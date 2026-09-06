/**
 * INT-142 — the encrypted draft store (acceptance clause 1).
 *
 * Persist / load / remove an intake draft, always through the envelope. The
 * three native concerns — key custody, blob I/O and randomness — are an
 * injected `DraftBackend`, so the store's behaviour (that only ciphertext
 * reaches disk, that a tampered blob is skipped not trusted, that sign-out
 * crypto-shreds) is provable in node with fakes. The production backend
 * (nativeBackend.ts) supplies SecureStore + expo-file-system + expo-crypto
 * behind a lazy import.
 *
 * A draft is typed / structured text only (a NoteState plus sync metadata):
 * raw audio never reaches this path (invariant 3), and no id is logged
 * (invariant 6).
 */
import { DraftDecryptError, isEncryptedEnvelope, openEnvelope, sealEnvelope } from "./envelope";
import type { DraftRecord } from "./reconcile";

export type { DraftRecord } from "./reconcile";

/** Custody of the device data-encryption key (DEK). Backed by the platform
 * keychain in production; the key never leaves the device and is never logged. */
export interface DraftVault {
  /** Get, creating on first use, the 32-byte DEK. */
  key(): Promise<Uint8Array>;
  /** Crypto-shred: delete the DEK so every sealed blob becomes unreadable. */
  destroy(): Promise<void>;
}

/** Opaque blob storage keyed by an id this module owns. Values are always
 * serialized `EncryptedEnvelope`s — never plaintext. */
export interface DraftBlobStore {
  write(id: string, data: string): Promise<void>;
  read(id: string): Promise<string | null>;
  remove(id: string): Promise<void>;
  list(): Promise<string[]>;
}

export interface DraftBackend {
  vault: DraftVault;
  blobs: DraftBlobStore;
  /** A fresh 12-byte GCM nonce per write. */
  randomIv(): Promise<Uint8Array>;
  /** Epoch ms — injected so tests can freeze the clock. */
  now(): number;
  /** Stable per-install id used as the conflict tiebreaker. */
  origin(): Promise<string>;
}

const ACTIVE_PREFIX = "draft__";
const CONFLICT_PREFIX = "conflict__";
const SUFFIX = ".enc";

/** A visit id must be a plain slug — no separator can reach the file path
 * (directory-traversal defence, CLAUDE.md "sanitize file paths"). */
function safeVisitId(visitId: string): string {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(visitId)) {
    throw new Error("unsafe draft visit id");
  }
  return visitId;
}

function activeBlobId(visitId: string): string {
  return `${ACTIVE_PREFIX}${safeVisitId(visitId)}${SUFFIX}`;
}

/** A conflict copy is addressed so it can never collide with the active draft
 * and is easy to enumerate; the losing version lives here rather than being
 * dropped (no silent data loss). */
export function conflictBlobId(visitId: string, at: number): string {
  return `${CONFLICT_PREFIX}${safeVisitId(visitId)}__${at}${SUFFIX}`;
}

function isActiveBlobId(id: string): boolean {
  return id.startsWith(ACTIVE_PREFIX) && id.endsWith(SUFFIX);
}

async function sealTo(backend: DraftBackend, id: string, record: DraftRecord): Promise<void> {
  const key = await backend.vault.key();
  const iv = await backend.randomIv();
  const envelope = sealEnvelope(key, iv, JSON.stringify(record));
  await backend.blobs.write(id, JSON.stringify(envelope));
}

async function openFrom(backend: DraftBackend, id: string): Promise<DraftRecord | null> {
  const raw = await backend.blobs.read(id);
  if (raw === null) {
    return null;
  }
  const key = await backend.vault.key();
  const parsed: unknown = JSON.parse(raw);
  if (!isEncryptedEnvelope(parsed)) {
    throw new DraftDecryptError("blob is not an envelope");
  }
  return JSON.parse(openEnvelope(key, parsed)) as DraftRecord;
}

/** Persist the active draft for its visit, sealed at rest. */
export async function persistDraft(backend: DraftBackend, record: DraftRecord): Promise<void> {
  await sealTo(backend, activeBlobId(record.visitId), record);
}

/** Persist the losing side of a conflict as a preserved copy. */
export async function persistConflictCopy(
  backend: DraftBackend,
  record: DraftRecord,
): Promise<string> {
  const id = conflictBlobId(record.visitId, backend.now());
  await sealTo(backend, id, record);
  return id;
}

/** Read the active draft for a visit, or null if none is stored. Throws
 * `DraftDecryptError` on tamper — the caller never sees a partial draft. */
export async function loadDraft(
  backend: DraftBackend,
  visitId: string,
): Promise<DraftRecord | null> {
  return openFrom(backend, activeBlobId(visitId));
}

export async function removeDraft(backend: DraftBackend, visitId: string): Promise<void> {
  await backend.blobs.remove(activeBlobId(visitId));
}

/** Every active draft, in blob-store order. A blob that cannot be decrypted is
 * skipped rather than trusted or surfaced as empty — an undecryptable draft is
 * unusable, and a crash on hydration would lose the readable ones with it. */
export async function loadAllDrafts(backend: DraftBackend): Promise<DraftRecord[]> {
  const ids = (await backend.blobs.list()).filter(isActiveBlobId);
  const drafts: DraftRecord[] = [];
  for (const id of ids) {
    try {
      const record = await openFrom(backend, id);
      if (record !== null) {
        drafts.push(record);
      }
    } catch {
      // corrupt or tampered: skip, never trust
    }
  }
  return drafts;
}

/** Sign-out hygiene: remove every draft blob (active and conflict copies) and
 * destroy the DEK, so nothing readable survives the session. */
export async function shredAllDrafts(backend: DraftBackend): Promise<void> {
  for (const id of await backend.blobs.list()) {
    await backend.blobs.remove(id);
  }
  await backend.vault.destroy();
}
