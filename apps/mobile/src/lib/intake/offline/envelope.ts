/**
 * INT-142 — envelope encryption for offline intake drafts.
 *
 * A typed intake draft persisted on the device (INT-142 acceptance clause 1)
 * is sealed at rest with AES-256-GCM. This module is the PURE half: it takes a
 * key and a nonce and returns / parses a self-describing envelope, so the rule
 * is testable in node with no device. The key itself is the device DEK held in
 * the platform keychain by the vault (see draftStore / nativeBackend) and
 * never appears here or on disk in the clear.
 *
 * AES-GCM comes from @noble/ciphers — the same MIT, pure-JS, audited family
 * (`@noble/curves`, `@noble/hashes`) the auth path already uses for signing,
 * chosen for the same reason: it behaves identically in the vitest node
 * environment and on the device, so what the tests prove is what ships. GCM's
 * authentication tag is what makes tamper detection real: a single flipped
 * byte fails `open` rather than returning a plausible-but-wrong draft.
 *
 * Only typed / structured text is ever sealed here. Raw audio never reaches
 * this path (invariant 3) and no identifier is logged (invariant 6).
 */
import { gcm } from "@noble/ciphers/aes.js";
import { bytesToHex, bytesToUtf8, hexToBytes, utf8ToBytes } from "@noble/ciphers/utils.js";

export const ENVELOPE_VERSION = 1;
/** AES-256 key size. */
export const KEY_BYTES = 32;
/** GCM standard nonce size. */
export const IV_BYTES = 12;

/** The at-rest artefact. Hex, not base64, so it needs no Buffer/btoa polyfill
 * on the device and round-trips byte-for-byte in node. `ct` includes GCM's
 * 16-byte authentication tag. */
export interface EncryptedEnvelope {
  v: number;
  alg: "A256GCM";
  iv: string;
  ct: string;
}

/** Why a draft could not be opened: the blob is not an envelope at all, or
 * it is one that will not decrypt (wrong key, tamper, malformed hex). */
export type DraftDecryptKind = "not_an_envelope" | "undecryptable";

/** Raised when a draft cannot be decrypted — wrong key, or tamper. The caller
 * treats an undecryptable blob as unusable (it fails closed), never as an
 * empty or partial draft. The kind IS the message — codes, never narrative,
 * as RecordsApiError does — so it carries no key, payload or id and no copy
 * that belongs in the catalogue (invariant 5). */
export class DraftDecryptError extends Error {
  readonly kind: DraftDecryptKind;

  constructor(kind: DraftDecryptKind = "undecryptable") {
    super(kind);
    this.kind = kind;
    this.name = "DraftDecryptError";
  }
}

export function sealEnvelope(
  key: Uint8Array,
  iv: Uint8Array,
  plaintext: string,
): EncryptedEnvelope {
  if (key.length !== KEY_BYTES) {
    throw new Error(`draft key must be ${KEY_BYTES} bytes`);
  }
  if (iv.length !== IV_BYTES) {
    throw new Error(`draft nonce must be ${IV_BYTES} bytes`);
  }
  const ct = gcm(key, iv).encrypt(utf8ToBytes(plaintext));
  return { v: ENVELOPE_VERSION, alg: "A256GCM", iv: bytesToHex(iv), ct: bytesToHex(ct) };
}

export function openEnvelope(key: Uint8Array, env: EncryptedEnvelope): string {
  if (key.length !== KEY_BYTES) {
    throw new Error(`draft key must be ${KEY_BYTES} bytes`);
  }
  if (!isEncryptedEnvelope(env)) {
    throw new DraftDecryptError("not_an_envelope");
  }
  try {
    const iv = hexToBytes(env.iv);
    const ct = hexToBytes(env.ct);
    return bytesToUtf8(gcm(key, iv).decrypt(ct));
  } catch {
    // GCM auth failure, a wrong key, or a malformed hex string all land here.
    // The message is deliberately generic — no key, no payload, no id.
    throw new DraftDecryptError();
  }
}

export function isEncryptedEnvelope(value: unknown): value is EncryptedEnvelope {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const env = value as Record<string, unknown>;
  return (
    typeof env.v === "number" &&
    env.alg === "A256GCM" &&
    typeof env.iv === "string" &&
    typeof env.ct === "string"
  );
}
