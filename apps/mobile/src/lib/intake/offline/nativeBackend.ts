/**
 * INT-142 — the production DraftBackend: the device half of the encrypted
 * draft store. Everything native lives here so the rest of the module stays
 * node-testable, and session.tsx loads this file only through a lazy
 * `import()` (the integrity-probe pattern), which is why the barrel does not
 * re-export it.
 *
 * Custody follows auth/tokens.ts to the letter: the data-encryption key (DEK)
 * and the per-install origin id live ONLY in expo-secure-store (Keychain /
 * Keystore, `WHEN_UNLOCKED_THIS_DEVICE_ONLY`), never a plain store, never a
 * log. The sealed draft blobs live under the document directory; each blob is
 * an `EncryptedEnvelope` and nothing else, so no plaintext draft ever touches
 * disk (invariant 3 for the typed draft, invariant 6 no-id-in-logs).
 */
import { bytesToHex, hexToBytes } from "@noble/ciphers/utils.js";
import * as Crypto from "expo-crypto";
import { Directory, File, Paths } from "expo-file-system";
import * as SecureStore from "expo-secure-store";

import { IV_BYTES, KEY_BYTES } from "./envelope";
import type { DraftBackend } from "./draftStore";

const DEK_SLOT = "intake.draft.dek";
const ORIGIN_SLOT = "intake.draft.origin";
const DRAFT_DIR = "intake-drafts";

function draftDirectory(): Directory {
  return new Directory(Paths.document, DRAFT_DIR);
}

function ensureDir(): Directory {
  const dir = draftDirectory();
  if (!dir.exists) {
    dir.create({ intermediates: true, idempotent: true });
  }
  return dir;
}

async function getOrCreateKey(): Promise<Uint8Array> {
  const stored = await SecureStore.getItemAsync(DEK_SLOT);
  if (stored !== null) {
    return hexToBytes(stored);
  }
  const fresh = await Crypto.getRandomBytesAsync(KEY_BYTES);
  await SecureStore.setItemAsync(DEK_SLOT, bytesToHex(fresh), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  return fresh;
}

/** The production backend. Constructed lazily; safe to call more than once. */
export function nativeDraftBackend(): DraftBackend {
  return {
    vault: {
      key: getOrCreateKey,
      async destroy() {
        await SecureStore.deleteItemAsync(DEK_SLOT);
      },
    },
    blobs: {
      async write(id, data) {
        const file = new File(ensureDir(), id);
        file.write(data);
      },
      async read(id) {
        const file = new File(draftDirectory(), id);
        return file.exists ? file.text() : null;
      },
      async remove(id) {
        const file = new File(draftDirectory(), id);
        if (file.exists) {
          file.delete();
        }
      },
      async list() {
        const dir = draftDirectory();
        if (!dir.exists) {
          return [];
        }
        return dir
          .list()
          .filter((entry): entry is File => entry instanceof File)
          .map((file) => file.name);
      },
    },
    async randomIv() {
      return Crypto.getRandomBytesAsync(IV_BYTES);
    },
    now() {
      return Date.now();
    },
    async origin() {
      const stored = await SecureStore.getItemAsync(ORIGIN_SLOT);
      if (stored !== null) {
        return stored;
      }
      const fresh = Crypto.randomUUID();
      await SecureStore.setItemAsync(ORIGIN_SLOT, fresh, {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      });
      return fresh;
    },
  };
}
