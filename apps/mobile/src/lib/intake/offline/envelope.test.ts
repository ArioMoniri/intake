/**
 * INT-142 — the at-rest envelope, proved as a pure function (no device, no
 * native module). AES-256-GCM over a UTF-8 string; the key is the device DEK
 * held in SecureStore by the vault, never here. Three properties matter:
 * round-trip, that the ciphertext carries NO plaintext (invariant 3/6 on the
 * typed draft), and that a single flipped byte fails the open (GCM auth), so a
 * tampered draft can never be read as if it were sound.
 */
import { describe, expect, it } from "vitest";

import {
  ENVELOPE_VERSION,
  IV_BYTES,
  KEY_BYTES,
  DraftDecryptError,
  isEncryptedEnvelope,
  openEnvelope,
  sealEnvelope,
} from "./envelope";

const key = (byte: number): Uint8Array => new Uint8Array(KEY_BYTES).fill(byte);
const iv = (byte: number): Uint8Array => new Uint8Array(IV_BYTES).fill(byte);

// A draft with a Turkish name and a free-text sentence: the exact PHI/PII a
// plaintext-on-disk scan would catch if the seal leaked it.
const PHI = JSON.stringify({
  visitId: "v1",
  note: {
    answers: [{ questionId: "complaint", values: ["baş ağrısı"], words: "Ayşe Yılmaz dün düştü" }],
  },
});

describe("envelope — AES-256-GCM seal/open", () => {
  it("round-trips a UTF-8 payload byte-for-byte", () => {
    const env = sealEnvelope(key(1), iv(2), PHI);
    expect(openEnvelope(key(1), env)).toBe(PHI);
  });

  it("stamps a versioned, self-describing header", () => {
    const env = sealEnvelope(key(1), iv(2), PHI);
    expect(env.v).toBe(ENVELOPE_VERSION);
    expect(env.alg).toBe("A256GCM");
    expect(isEncryptedEnvelope(env)).toBe(true);
  });

  it("carries no plaintext PHI/PII in the serialized envelope (invariant 3/6)", () => {
    const env = sealEnvelope(key(7), iv(9), PHI);
    const onDisk = JSON.stringify(env);
    expect(onDisk).not.toContain("baş ağrısı");
    expect(onDisk).not.toContain("Ayşe");
    expect(onDisk).not.toContain("düştü");
    expect(onDisk).not.toContain("complaint");
  });

  it("produces different ciphertext for different nonces (no ECB-style leak)", () => {
    const a = sealEnvelope(key(1), iv(2), PHI);
    const b = sealEnvelope(key(1), iv(3), PHI);
    expect(a.ct).not.toBe(b.ct);
  });

  it("refuses to open a payload sealed under a different key", () => {
    const env = sealEnvelope(key(1), iv(2), PHI);
    expect(() => openEnvelope(key(9), env)).toThrow(DraftDecryptError);
  });

  it("refuses a tampered ciphertext (one flipped byte fails GCM auth)", () => {
    const env = sealEnvelope(key(1), iv(2), PHI);
    const bytes = [...env.ct];
    // flip the first hex nibble deterministically
    bytes[0] = bytes[0] === "a" ? "b" : "a";
    const tampered = { ...env, ct: bytes.join("") };
    expect(() => openEnvelope(key(1), tampered)).toThrow(DraftDecryptError);
  });

  it("rejects a key or nonce of the wrong length rather than sealing weakly", () => {
    expect(() => sealEnvelope(new Uint8Array(16), iv(2), PHI)).toThrow();
    expect(() => sealEnvelope(key(1), new Uint8Array(8), PHI)).toThrow();
  });

  it("isEncryptedEnvelope rejects arbitrary objects", () => {
    expect(isEncryptedEnvelope(null)).toBe(false);
    expect(isEncryptedEnvelope({ iv: "00", ct: "00" })).toBe(false);
    expect(isEncryptedEnvelope({ v: 1, alg: "A256GCM", iv: "00", ct: "00" })).toBe(true);
  });
});
