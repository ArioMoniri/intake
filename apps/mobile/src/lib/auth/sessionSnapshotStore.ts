/**
 * SecureStore custody for the restore snapshot (INT-131), same class as
 * tokens.ts: the record is Keychain / Keystore-encrypted, WHEN_UNLOCKED and
 * THIS_DEVICE_ONLY — so it never rides an iCloud/Keystore backup to another
 * device, and is unreadable while the phone is locked. See sessionSnapshot.ts
 * for the shape, the codec and the data-inventory annotation.
 *
 * This module is the ONLY thing in the restore path that imports a native
 * module. session.tsx reaches it through a lazy `import()` (the integrity-probe
 * pattern in that file), so importing session.tsx from node — as the unit
 * suite does — never loads expo-secure-store.
 */
import * as SecureStore from "expo-secure-store";

import {
  SESSION_SNAPSHOT_SLOT,
  decodeSnapshot,
  encodeSnapshot,
  type RestorableSession,
} from "./sessionSnapshot";

// One writer for one key: verify hands the shell a baseline, then the sync
// resolves and writes the visits and the name in quick succession. Serialising
// them in call order means the LAST write wins deterministically — the full
// name+visits record — rather than depending on the native store to complete
// two overlapping writes in the order they were issued. There is one
// SessionProvider for the app's life, so module scope is the session's scope.
let writeQueue: Promise<unknown> = Promise.resolve();

function serialize<T>(op: () => Promise<T>): Promise<T> {
  const run = writeQueue.then(op, op);
  writeQueue = run.catch(() => {});
  return run;
}

export async function saveSessionSnapshot(snapshot: RestorableSession): Promise<void> {
  const encoded = encodeSnapshot(snapshot);
  await serialize(() =>
    SecureStore.setItemAsync(SESSION_SNAPSHOT_SLOT, encoded, {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    }),
  );
}

export async function loadSessionSnapshot(): Promise<RestorableSession | null> {
  try {
    return decodeSnapshot(await SecureStore.getItemAsync(SESSION_SNAPSHOT_SLOT));
  } catch {
    // A read that throws (no keychain, locked device on some OSes) restores no
    // session rather than crashing the launch — the same fail-open the codec
    // gives a corrupt record.
    return null;
  }
}

export async function clearSessionSnapshot(): Promise<void> {
  await serialize(() => SecureStore.deleteItemAsync(SESSION_SNAPSHOT_SLOT));
}
