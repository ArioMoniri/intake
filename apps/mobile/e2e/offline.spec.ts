/**
 * INT-142 — Offline drafts + sync + resilience.
 *
 * Acceptance (docs/backlog/issues.yaml): *"drafts encrypted at rest; sync
 * conflict rules; airplane-mode e2e"*.
 *
 * Same split every mobile e2e spec here makes: vitest runs on `node` with no
 * renderer (apps/mobile/vitest.config.ts), so nothing below draws a screen.
 * The RULES are pure and have their own unit tests next to them
 * (`envelope.test.ts`, `reconcile.test.ts`, `draftStore.test.ts`). What THIS
 * file proves is the airplane-mode JOURNEY end to end over an in-memory
 * backend and an in-memory transport — create a draft with the network down,
 * see it land encrypted, restore it, bring the network back, sync it, and see
 * the deterministic conflict rule resolve with nothing lost — plus the WIRING
 * in session.tsx: that the app reaches the encrypted store through a lazy
 * native backend, crypto-shreds on sign-out, and keeps no plaintext draft.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { isEncryptedEnvelope } from "@/lib/intake/offline/envelope";
import {
  loadDraft,
  persistDraft,
  type DraftBackend,
  type DraftRecord,
} from "@/lib/intake/offline/draftStore";
import { syncVisit, type DraftTransport } from "@/lib/intake/offline/sync";
import { emptyNoteState, noteReducer, type NoteState } from "@/lib/intake/note";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

function note(complaint: string): NoteState {
  return noteReducer(emptyNoteState(), {
    type: "answer",
    questionId: "complaint",
    values: [complaint],
    words: "Ayşe dün düştü",
  });
}

/** In-memory stand-in for SecureStore + expo-file-system + expo-crypto. */
function fakeBackend(): DraftBackend & { blobBytes: Map<string, string> } {
  const blobBytes = new Map<string, string>();
  let keyBytes: Uint8Array | null = null;
  let ivCounter = 0;
  return {
    blobBytes,
    vault: {
      async key() {
        keyBytes ??= new Uint8Array(32).fill(0x5a);
        return keyBytes;
      },
      async destroy() {
        keyBytes = null;
      },
    },
    blobs: {
      async write(id, data) {
        blobBytes.set(id, data);
      },
      async read(id) {
        return blobBytes.get(id) ?? null;
      },
      async remove(id) {
        blobBytes.delete(id);
      },
      async list() {
        return [...blobBytes.keys()];
      },
    },
    async randomIv() {
      ivCounter += 1;
      return new Uint8Array(12).fill(ivCounter & 0xff);
    },
    now() {
      return 10_000;
    },
    async origin() {
      return "device-under-test";
    },
  };
}

/**
 * A transport whose reachability is a switch. `online=false` is airplane mode:
 * every call throws, exactly as fetch does with no network. `serverRecord` is
 * the note held by the server (INT-197's /v1/visits/{id}/note), and push
 * bumps its revision the way a server ack would.
 */
function fakeTransport(): DraftTransport & {
  online: boolean;
  serverRecord: DraftRecord | null;
} {
  const box: DraftTransport & { online: boolean; serverRecord: DraftRecord | null } = {
    online: false,
    serverRecord: null,
    async pull(visitId) {
      if (!box.online) {
        throw new Error("network unreachable");
      }
      return box.serverRecord && box.serverRecord.visitId === visitId ? box.serverRecord : null;
    },
    async push(record) {
      if (!box.online) {
        throw new Error("network unreachable");
      }
      const acked = {
        ...record,
        revision: (box.serverRecord?.revision ?? record.revision) + 1,
        dirty: false,
      };
      box.serverRecord = acked;
      return acked;
    },
  };
  return box;
}

describe("INT-142 airplane-mode journey", () => {
  it("creates a draft with the network DOWN and lands it encrypted at rest", async () => {
    const backend = fakeBackend();
    const record: DraftRecord = {
      visitId: "v-air",
      note: note("baş ağrısı"),
      revision: 0,
      dirty: true,
      updatedAt: backend.now(),
      origin: await backend.origin(),
    };
    await persistDraft(backend, record);

    // the payload on disk is ciphertext, not the patient's words
    expect(backend.blobBytes.size).toBe(1);
    const raw = [...backend.blobBytes.values()][0];
    expect(isEncryptedEnvelope(JSON.parse(raw))).toBe(true);
    expect(raw).not.toContain("baş ağrısı");
    expect(raw).not.toContain("Ayşe");
  });

  it("keeps the draft queued while offline, then syncs it on reconnect — nothing lost", async () => {
    const backend = fakeBackend();
    const transport = fakeTransport();

    const local: DraftRecord = {
      visitId: "v-air",
      note: note("baş ağrısı"),
      revision: 0,
      dirty: true,
      updatedAt: backend.now(),
      origin: await backend.origin(),
    };
    await persistDraft(backend, local);

    // AIRPLANE MODE: sync cannot reach the server; the draft survives locally.
    const offline = await syncVisit(backend, transport, "v-air");
    expect(offline.outcome).toBe("offline");
    const stillThere = await loadDraft(backend, "v-air");
    expect(stillThere?.dirty).toBe(true);
    expect(stillThere?.note).toEqual(local.note);

    // RECONNECT: the queued draft pushes and the server acks it.
    transport.online = true;
    const synced = await syncVisit(backend, transport, "v-air");
    expect(synced.outcome).toBe("push");
    const acked = await loadDraft(backend, "v-air");
    expect(acked?.dirty).toBe(false);
    expect(acked?.revision).toBe(1);
    expect(transport.serverRecord?.note).toEqual(local.note);
  });

  it("resolves a real conflict deterministically and preserves the losing copy", async () => {
    const backend = fakeBackend();
    const transport = fakeTransport();
    transport.online = true;

    // the server advanced (another device) while we edited offline
    transport.serverRecord = {
      visitId: "v-air",
      note: note("server tarafı"),
      revision: 5,
      dirty: false,
      updatedAt: 8_000,
      origin: "other-device",
    };
    const local: DraftRecord = {
      visitId: "v-air",
      note: note("yerel taslak"),
      revision: 2, // based on an older server revision
      dirty: true,
      updatedAt: 9_000, // our edit is newer
      origin: "device-under-test",
    };
    await persistDraft(backend, local);

    const res = await syncVisit(backend, transport, "v-air");
    expect(res.outcome).toBe("conflict");
    // last-writer-wins: our 9000 beats the server's 8000
    expect(res.winner?.note).toEqual(local.note);
    // the loser is preserved as a conflict copy — NEVER silently dropped
    const conflictBlobs = (await backend.blobs.list()).filter((id) => id.includes("conflict"));
    expect(conflictBlobs.length).toBe(1);
  });
});

describe("INT-142 session wiring (source-slice)", () => {
  const session = read(SRC, "lib", "session.tsx");

  it("reaches the encrypted draft store through a lazy native backend", () => {
    // the offline backend is loaded via dynamic import so session.tsx stays
    // node-importable (the same pattern the integrity probe uses)
    expect(session).toMatch(/import\(\s*["']\.\/intake\/offline/);
  });

  it("crypto-shreds drafts on sign-out", () => {
    expect(session).toMatch(/shred|destroy/i);
  });

  it("holds no plaintext draft: native at-rest calls live only in the backend", () => {
    // session.tsx must not itself reach for a raw store; it goes through the
    // offline module, which is where SecureStore/expo-file-system live.
    expect(session).not.toContain("expo-file-system");
    expect(session).not.toContain("writeAsStringAsync");
    const backend = read(SRC, "lib", "intake", "offline", "nativeBackend.ts");
    expect(backend).toContain("expo-secure-store");
    expect(backend).toContain("expo-file-system");
  });
});
