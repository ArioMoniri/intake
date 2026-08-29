/**
 * DPoP proof assembly (RFC 9449) — pure and node-testable (INT-131).
 *
 * The signing key is a P-256 scalar supplied by the caller (custody lives
 * in dpop.ts, inside SecureStore); signatures are deterministic RFC 6979
 * ES256 via @noble/curves, so no randomness is needed here. The server
 * verifies these proofs byte-for-byte (services/api dpop.py): compact JWS,
 * header {typ: "dpop+jwt", alg: "ES256", jwk}, claims {htm, htu, iat, jti}
 * plus `ath` (the access-token hash) on resource requests.
 */
import { p256 } from "@noble/curves/nist.js";
import { sha256 } from "@noble/hashes/sha2.js";

export interface EcJwk {
  kty: "EC";
  crv: "P-256";
  x: string;
  y: string;
}

const B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

/** base64url without padding, dependency-free (no Buffer in Hermes). */
export function b64url(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i];
    const b = i + 1 < bytes.length ? bytes[i + 1] : undefined;
    const c = i + 2 < bytes.length ? bytes[i + 2] : undefined;
    out += B64_CHARS[a >> 2];
    out += B64_CHARS[((a & 0x03) << 4) | ((b ?? 0) >> 4)];
    if (b !== undefined) {
      out += B64_CHARS[((b & 0x0f) << 2) | ((c ?? 0) >> 6)];
    }
    if (c !== undefined) {
      out += B64_CHARS[c & 0x3f];
    }
  }
  return out;
}

function utf8(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

/** Public JWK for a P-256 secret key (uncompressed point → x/y coordinates). */
export function publicJwk(secretKey: Uint8Array): EcJwk {
  const point = p256.getPublicKey(secretKey, false);
  return {
    kty: "EC",
    crv: "P-256",
    x: b64url(point.slice(1, 33)),
    y: b64url(point.slice(33, 65)),
  };
}

export interface ProofInput {
  method: string;
  url: string;
  iatSeconds: number;
  jti: string;
  secretKey: Uint8Array;
  /** Set on resource requests: binds the proof to the token (ath claim). */
  accessToken?: string;
}

/** One compact-JWS DPoP proof. */
export function buildDpopProof(input: ProofInput): string {
  const header = { typ: "dpop+jwt", alg: "ES256", jwk: publicJwk(input.secretKey) };
  const claims: Record<string, unknown> = {
    htm: input.method.toUpperCase(),
    htu: input.url,
    iat: Math.floor(input.iatSeconds),
    jti: input.jti,
  };
  if (input.accessToken !== undefined) {
    claims.ath = b64url(sha256(utf8(input.accessToken)));
  }
  const signingInput = `${b64url(utf8(JSON.stringify(header)))}.${b64url(
    utf8(JSON.stringify(claims)),
  )}`;
  const signature = p256.sign(utf8(signingInput), input.secretKey, { prehash: true });
  return `${signingInput}.${b64url(signature)}`;
}
