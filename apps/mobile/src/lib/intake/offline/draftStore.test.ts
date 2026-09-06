/**
 * INT-142 — the draft store, proved against an in-memory backend (the fakes
 * stand in for SecureStore + expo-file-system + expo-crypto, which the
 * production backend supplies behind a lazy native import). What is asserted
 * here is exactly what the acceptance's first clause claims: a persisted draft
 * is encrypted at rest, so the bytes the blob store holds are ciphertext with
 * no plaintext PHI, and only the vault key can bring the draft back.
 */
import { describe, expect, it } from "vitest";

import { emptyNoteState, noteReducer, type NoteState } from "../note";
import { isEncryptedEnvelope } from "./envelope";
import {
  loadAllDrafts,
  loadDraft,
  persistDraft,
  removeDraft,
  shredAllDrafts,
  type DraftBackend,
  type DraftRecord,
} from "./draftStore";

function note(complaint: string, words?: string): NoteState {
  return noteReducer(emptyNoteState(), {
    type: "answer",
    questionId: "complaint",
    values: [complaint],
    words,
  });
}

/** An in-memory backend that mimics the native one without any device. */
function fakeBackend(): DraftBackend & {
  blobBytes: Map<string, string>;
  keyBytes: Uint8Array | null;
} {
  const blobBytes = new Map<string, string>();
  let keyBytes: Uint8Array | null = null;
  let ivCounter = 0;
  const backend: DraftBackend & { blobBytes: Map<string, string>; keyBytes: Uint8Array | null } = {
    blobBytes,
    keyBytes,
    vault: {
      async key() {
        if (keyBytes === null) {
          keyBytes = new Uint8Array(32).fill(0xab);
          backend.keyBytes = keyBytes;
        }
        return keyBytes;
      },
      async destroy() {
        keyBytes = null;
        backend.keyBytes = null;
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
      return 1234;
    },
    async origin() {
      return "device-test";
    },
  };
  return backend;
}

function draft(over: Partial<DraftRecord> = {}): DraftRecord {
  return {
    visitId: "visit-42",
    note: note("baş ağrısı", "Ayşe dün düştü"),
    revision: 0,
    dirty: true,
    updatedAt: 1234,
    origin: "device-test",
    ...over,
  };
}

describe("draftStore — encrypted at rest", () => {
  it("persists a draft and reads it back identically", async () => {
    const backend = fakeBackend();
    const record = draft();
    await persistDraft(backend, record);
    const back = await loadDraft(backend, "visit-42");
    expect(back).toEqual(record);
  });

  it("writes ONLY ciphertext to the blob store — no plaintext PHI on disk", async () => {
    const backend = fakeBackend();
    await persistDraft(backend, draft());
    expect(backend.blobBytes.size).toBe(1);
    for (const raw of backend.blobBytes.values()) {
      expect(raw).not.toContain("baş ağrısı");
      expect(raw).not.toContain("Ayşe");
      expect(raw).not.toContain("düştü");
      expect(raw).not.toContain("complaint");
      // what IS on disk is a well-formed encrypted envelope
      expect(isEncryptedEnvelope(JSON.parse(raw))).toBe(true);
    }
  });

  it("returns null for a visit with no persisted draft", async () => {
    const backend = fakeBackend();
    expect(await loadDraft(backend, "nope")).toBeNull();
  });

  it("removes a draft's blob on delete", async () => {
    const backend = fakeBackend();
    await persistDraft(backend, draft());
    await removeDraft(backend, "visit-42");
    expect(await loadDraft(backend, "visit-42")).toBeNull();
    expect(backend.blobBytes.size).toBe(0);
  });

  it("loads every persisted draft, skipping any that cannot be decrypted", async () => {
    const backend = fakeBackend();
    await persistDraft(backend, draft({ visitId: "a" }));
    await persistDraft(backend, draft({ visitId: "b", note: note("karın ağrısı") }));
    // a corrupt blob must never crash hydration nor be silently trusted
    const anyId = (await backend.blobs.list())[0];
    await backend.blobs.write(
      anyId,
      JSON.stringify({ v: 1, alg: "A256GCM", iv: "00".repeat(12), ct: "dead" }),
    );
    const all = await loadAllDrafts(backend);
    expect(all.map((d) => d.visitId).sort()).toEqual(["b"]);
  });

  it("crypto-shreds on sign-out: blobs gone AND the vault key destroyed", async () => {
    const backend = fakeBackend();
    await persistDraft(backend, draft());
    await backend.vault.key(); // force key materialisation
    await shredAllDrafts(backend);
    expect(backend.blobBytes.size).toBe(0);
    expect(backend.keyBytes).toBeNull();
  });

  it("refuses a visit id that could escape the draft directory (path safety)", async () => {
    const backend = fakeBackend();
    await expect(persistDraft(backend, draft({ visitId: "../../etc/passwd" }))).rejects.toThrow();
    await expect(loadDraft(backend, "../secrets")).rejects.toThrow();
  });
});
