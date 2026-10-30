/**
 * INT-587 — where a queued note waits between app runs.
 *
 * The outbox rides INT-142's encrypted draft store rather than opening a
 * second one: the same `DraftBackend` (DEK in the Keychain/Keystore, sealed
 * blobs under the document directory), the same AES-256-GCM envelope, a
 * distinct blob prefix. Two consequences follow without new code:
 *
 * - only ciphertext reaches disk — a queued note is the same typed text the
 *   draft already holds, sealed the same way, and no new category of data is
 *   persisted (the delivery stage and the server visit id are about the note,
 *   not new facts about the patient);
 * - sign-out's crypto-shred (`shredAllDrafts`) removes every blob in the
 *   directory and destroys the DEK, so a queued note never outlives the
 *   session that sent it. That, and the kiosk wipe, are the only ways an
 *   undelivered note leaves the phone other than being delivered — both are
 *   explicit acts that end the session's data by design (INT-142, INT-143).
 *
 * In kiosk mode (`memoryOutbox`) nothing is written at all: a shared clinic
 * device never persists a patient's note (INT-143).
 */
import {
  DraftDecryptError,
  isEncryptedEnvelope,
  openEnvelope,
  sealEnvelope,
} from "../offline/envelope";
import type { DraftBackend } from "../offline/draftStore";
import { parseItem, type DeliveryItem } from "./outbox";

export interface OutboxPersistence {
  save(item: DeliveryItem): Promise<void>;
  remove(visitId: string): Promise<void>;
  /** Every stored item that still validates; a tampered blob is skipped. */
  loadAll(): Promise<DeliveryItem[]>;
}

const PREFIX = "outbox__";
const SUFFIX = ".enc";

/** The visit id becomes part of a file name: a plain slug or nothing. */
function blobId(visitId: string): string {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(visitId)) {
    throw new Error("unsafe outbox visit id");
  }
  return `${PREFIX}${visitId}${SUFFIX}`;
}

function isOutboxBlob(id: string): boolean {
  return id.startsWith(PREFIX) && id.endsWith(SUFFIX);
}

/** The production outbox: sealed blobs through the INT-142 backend. */
export function sealedOutbox(backend: DraftBackend): OutboxPersistence {
  return {
    async save(item) {
      const key = await backend.vault.key();
      const iv = await backend.randomIv();
      const envelope = sealEnvelope(key, iv, JSON.stringify(item));
      await backend.blobs.write(blobId(item.visitId), JSON.stringify(envelope));
    },
    async remove(visitId) {
      await backend.blobs.remove(blobId(visitId));
    },
    async loadAll() {
      const items: DeliveryItem[] = [];
      const ids = (await backend.blobs.list()).filter(isOutboxBlob);
      if (ids.length === 0) {
        return items;
      }
      const key = await backend.vault.key();
      for (const id of ids) {
        try {
          const raw = await backend.blobs.read(id);
          if (raw === null) {
            continue;
          }
          const parsed: unknown = JSON.parse(raw);
          if (!isEncryptedEnvelope(parsed)) {
            throw new DraftDecryptError("not_an_envelope");
          }
          const item = parseItem(JSON.parse(openEnvelope(key, parsed)));
          if (item !== null) {
            items.push(item);
          }
        } catch {
          // tampered, undecryptable or off-shape: never trusted, never sent
        }
      }
      return items;
    },
  };
}

/** Kiosk mode: the outbox lives in memory only. */
export function memoryOutbox(): OutboxPersistence {
  const items = new Map<string, DeliveryItem>();
  return {
    async save(item) {
      items.set(item.visitId, item);
    },
    async remove(visitId) {
      items.delete(visitId);
    },
    async loadAll() {
      return [...items.values()];
    },
  };
}
