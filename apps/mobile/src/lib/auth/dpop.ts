/**
 * DPoP key custody (INT-131, files/10 §2: refresh tokens device-bound).
 *
 * One P-256 secret key per install, generated from expo-crypto randomness
 * and kept ONLY in SecureStore (Keychain / Android Keystore-encrypted
 * storage) — it never touches any plain key-value store, module state that
 * outlives the call, or any log. Proof assembly is the pure jws.ts (deterministic
 * RFC 6979 signing via @noble/curves p256, so no RNG on the signing path).
 *
 * Honesty note: SecureStore holds the scalar as protected DATA — the key is
 * software-held. A NON-EXPORTABLE hardware key (Secure Enclave / StrongBox)
 * needs a first-party native module in a dev build (files/10 §4 budgets it
 * as its own issue); until that lands this is device-bound custody, not
 * hardware attestation, and nothing here claims otherwise.
 */
import { p256 } from "@noble/curves/nist.js";
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";

import { buildDpopProof } from "./jws";

const KEY_SLOT = "intake.auth.dpop.secret";

const HEX = "0123456789abcdef";

function toHex(bytes: Uint8Array): string {
  let out = "";
  for (const b of bytes) {
    out += HEX[b >> 4] + HEX[b & 0x0f];
  }
  return out;
}

function fromHex(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

async function getOrCreateSecretKey(): Promise<Uint8Array> {
  const stored = await SecureStore.getItemAsync(KEY_SLOT);
  if (stored !== null) {
    return fromHex(stored);
  }
  let secret = new Uint8Array(Crypto.getRandomBytes(32));
  while (!p256.utils.isValidSecretKey(secret)) {
    secret = new Uint8Array(Crypto.getRandomBytes(32));
  }
  await SecureStore.setItemAsync(KEY_SLOT, toHex(secret), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  return secret;
}

export interface DpopRequest {
  method: string;
  url: string;
  accessToken?: string;
}

/** One proof for one request (fresh jti; the server enforces single use). */
export async function dpopProof(request: DpopRequest): Promise<string> {
  const secretKey = await getOrCreateSecretKey();
  return buildDpopProof({
    method: request.method,
    url: request.url,
    iatSeconds: Date.now() / 1000,
    jti: toHex(new Uint8Array(Crypto.getRandomBytes(16))),
    secretKey,
    accessToken: request.accessToken,
  });
}

/** Sign-out hygiene: a new session binds to a fresh key. */
export async function resetDpopKey(): Promise<void> {
  await SecureStore.deleteItemAsync(KEY_SLOT);
}
