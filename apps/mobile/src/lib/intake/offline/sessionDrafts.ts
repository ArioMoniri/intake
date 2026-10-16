/**
 * INT-142 — the session's binding to the encrypted draft store.
 *
 * session.tsx loads this file through a lazy `import()` (the integrity-probe
 * pattern) so the provider stays node-importable; the native backend and its
 * expo modules never reach the vitest node environment. Everything here is
 * fire-and-forget from the UI's point of view: a persist that fails leaves the
 * in-memory draft untouched, and nothing here logs an id or a value
 * (invariant 6).
 *
 * Drafts are scoped to the signed-in account on hydration, and sign-out
 * crypto-shreds every blob and the DEK, so a draft never outlives the session
 * that owns it or surfaces under another account.
 */
import { restoreNote, type NoteState } from "../note";
import {
  loadAllDrafts,
  loadDraft,
  persistDraft,
  removeDraft,
  shredAllDrafts,
  type DraftBackend,
} from "./draftStore";
import { nativeDraftBackend } from "./nativeBackend";

let backend: DraftBackend | null = null;

function resolveBackend(): DraftBackend {
  backend ??= nativeDraftBackend();
  return backend;
}

/** Persist one visit's draft, sealed at rest, carrying its sync revision
 * forward and marking it dirty (unsynced local edit). */
export async function persistNoteDraft(
  accountId: string,
  visitId: string,
  note: NoteState,
): Promise<void> {
  const be = resolveBackend();
  const existing = await loadDraft(be, visitId).catch(() => null);
  await persistDraft(be, {
    visitId,
    note,
    accountId,
    revision: existing?.revision ?? 0,
    dirty: true,
    updatedAt: be.now(),
    origin: await be.origin(),
  });
}

/** Restore this account's drafts after an app restart. Other accounts' drafts
 * (should any survive) are never surfaced. INT-510: each note is made whole by
 * `restoreNote`, so a send that was queued (or in flight) when the app closed
 * comes back still waiting to be sent — and a pre-INT-510 "sent" that never
 * reached a server comes back a draft. */
export async function hydrateAccountDrafts(accountId: string): Promise<Record<string, NoteState>> {
  const drafts = await loadAllDrafts(resolveBackend());
  const notes: Record<string, NoteState> = {};
  for (const draft of drafts) {
    if (draft.accountId === accountId) {
      notes[draft.visitId] = restoreNote(draft.note);
    }
  }
  return notes;
}

/** Drop one visit's draft (e.g. after a successful send). */
export async function removeNoteDraft(visitId: string): Promise<void> {
  await removeDraft(resolveBackend(), visitId);
}

/** Sign-out hygiene: crypto-shred every draft and the DEK. */
export async function shredDrafts(): Promise<void> {
  await shredAllDrafts(resolveBackend());
  backend = null;
}
