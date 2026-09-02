import { p256 } from "@noble/curves/nist.js";
import { sha256 } from "@noble/hashes/sha2.js";
import { describe, expect, it } from "vitest";

import { b64url, buildDpopProof, publicJwk } from "./jws";

const SECRET = p256.utils.randomSecretKey();

function decodeSegment(segment: string): Record<string, unknown> {
  const pad = "=".repeat((4 - (segment.length % 4)) % 4);
  const json = Buffer.from(segment.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64");
  return JSON.parse(json.toString("utf8")) as Record<string, unknown>;
}

describe("buildDpopProof (RFC 9449 client half)", () => {
  it("emits the fixed header and the request-bound claims", () => {
    const proof = buildDpopProof({
      method: "post",
      url: "http://testserver/v1/auth/otp/verify",
      iatSeconds: 1_756_400_000,
      jti: "jti-1",
      secretKey: SECRET,
    });
    const [headerB64, claimsB64, signatureB64] = proof.split(".");
    const header = decodeSegment(headerB64);
    expect(header.typ).toBe("dpop+jwt");
    expect(header.alg).toBe("ES256");
    expect((header.jwk as { crv: string }).crv).toBe("P-256");
    const claims = decodeSegment(claimsB64);
    expect(claims.htm).toBe("POST");
    expect(claims.htu).toBe("http://testserver/v1/auth/otp/verify");
    expect(claims.iat).toBe(1_756_400_000);
    expect(claims.ath).toBeUndefined();
    expect(signatureB64.length).toBeGreaterThan(80); // 64 raw bytes, b64url
  });

  it("signature verifies against the embedded public key", () => {
    const proof = buildDpopProof({
      method: "GET",
      url: "http://testserver/v1/visits",
      iatSeconds: 1_756_400_000,
      jti: "jti-2",
      secretKey: SECRET,
      accessToken: "an-access-token",
    });
    const [headerB64, claimsB64, signatureB64] = proof.split(".");
    const pad = "=".repeat((4 - (signatureB64.length % 4)) % 4);
    const signature = new Uint8Array(
      Buffer.from(signatureB64.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64"),
    );
    const message = new TextEncoder().encode(`${headerB64}.${claimsB64}`);
    const ok = p256.verify(signature, message, p256.getPublicKey(SECRET, false), {
      prehash: true,
    });
    expect(ok).toBe(true);
    const claims = decodeSegment(claimsB64);
    const expectedAth = b64url(sha256(new TextEncoder().encode("an-access-token")));
    expect(claims.ath).toBe(expectedAth);
  });

  it("publicJwk coordinates are 32-byte b64url values", () => {
    const jwk = publicJwk(SECRET);
    expect(jwk.x).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(jwk.y).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });
});
