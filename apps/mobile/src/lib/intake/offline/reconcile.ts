/**
 * INT-142 — the sync conflict rule (acceptance clause 2), as a pure,
 * deterministic function so it can be exercised over every branch without a
 * device or a network.
 *
 * The device holds the authoritative offline draft; the server (INT-197's
 * /v1/visits/{id}/note) holds the copy last saved from any device. When
 * connectivity returns the two must be reconciled. The one property the whole
 * feature rests on is NO SILENT DATA LOSS: every path keeps the local draft,
 * adopts the remote, or — when both diverged — declares a conflict and hands
 * BOTH copies back so the loser can be preserved. Nothing is ever overwritten
 * with the losing version gone.
 *
 * The rule, in order:
 *   1. remote absent            → push (local is the only copy)
 *   2. local absent             → take-remote (adopt the server copy)
 *   3. local clean (no offline edits):
 *        remote.revision > base → take-remote
 *        else                   → in-sync
 *   4. local dirty (offline edits exist):
 *        remote not past base   → push (fast-forward; server never moved)
 *        remote past base       → conflict → last-writer-wins by updatedAt,
 *                                  ties broken by origin ascending, loser kept
 *
 * `revision` is the server-assigned version the local copy derives from; a
 * never-synced draft is revision 0. `dirty` means there are local edits the
 * server has not acknowledged. `updatedAt` (epoch ms) is the last-writer-wins
 * signal and `origin` (stable per-install id) is the deterministic tiebreaker
 * — never a coin flip, so the same inputs always resolve the same way.
 */
import type { NoteState } from "../note";

export interface DraftMeta {
  /** Server-assigned base revision this copy derives from; 0 = never synced. */
  revision: number;
  /** Local edits not yet acknowledged by the server. */
  dirty: boolean;
  /** Epoch ms of the last local edit — the last-writer-wins ordering signal. */
  updatedAt: number;
  /** Stable per-install id — the deterministic conflict tiebreaker. */
  origin: string;
}

export interface DraftRecord extends DraftMeta {
  visitId: string;
  note: NoteState;
  /**
   * The account the draft belongs to. Wiring-only (session hydration scopes a
   * device's drafts to the signed-in patient so one account never surfaces
   * another's). Optional and ignored by the conflict rule, which reconciles a
   * single visit's two copies and never crosses accounts.
   */
  accountId?: string;
}

export type SyncOutcome = "in-sync" | "push" | "take-remote" | "conflict";

export interface Resolution {
  outcome: SyncOutcome;
  /** The copy to keep as the active draft. */
  winner: DraftRecord;
  /** The diverged copy to preserve (conflict only); null otherwise. */
  loser: DraftRecord | null;
}

/** last-writer-wins: newer updatedAt wins; a tie breaks by origin ascending. */
function laterWins(a: DraftRecord, b: DraftRecord): DraftRecord {
  if (a.updatedAt !== b.updatedAt) {
    return a.updatedAt > b.updatedAt ? a : b;
  }
  return a.origin <= b.origin ? a : b;
}

export function reconcile(local: DraftRecord | null, remote: DraftRecord | null): Resolution {
  if (local === null && remote === null) {
    throw new Error("reconcile needs at least one side");
  }
  if (remote === null) {
    return { outcome: "push", winner: local as DraftRecord, loser: null };
  }
  if (local === null) {
    return { outcome: "take-remote", winner: remote, loser: null };
  }

  if (!local.dirty) {
    if (remote.revision > local.revision) {
      return { outcome: "take-remote", winner: remote, loser: null };
    }
    return { outcome: "in-sync", winner: local, loser: null };
  }

  // local has offline edits
  if (remote.revision <= local.revision) {
    // the server has not moved past the base our edits sit on: fast-forward
    return { outcome: "push", winner: local, loser: null };
  }

  // both diverged: keep both, pick a deterministic winner
  const winner = laterWins(local, remote);
  const loser = winner === local ? remote : local;
  return { outcome: "conflict", winner, loser };
}
