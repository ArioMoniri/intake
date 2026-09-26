/**
 * INT-344 — the client half of device attestation, as pure logic.
 *
 * Acceptance (GitHub #543): "iOS release builds attest with App Attest …; the
 * client never sends a dev-unattested mode outside __DEV__". The native module
 * (@expo/app-integrity) never loads here — vitest is node-only — so the key
 * lifecycle runs against in-memory ports, and what reaches the wire is pinned
 * as the exact strings the server (services/api attestation.py) rebuilds.
 */
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import {
  AttestationFailureError,
  type AttestationMode,
  type AttestationPorts,
  type KeyRegistration,
  appAttestHeader,
  attestationClientData,
  attestationMessageKey,
  buildAttestationHeader,
  decodeAttestKey,
  devUnattestedHeader,
  encodeAttestKey,
  isAttestationRefusal,
  nativeFailure,
  selectAttestationMode,
  shouldReattest,
} from "./attestationPlan";

describe("mode selection", () => {
  const platforms = ["ios", "android", "web", "windows", "macos"];

  it("never selects dev-unattested outside __DEV__, whatever the device says", () => {
    for (const platform of platforms) {
      for (const appAttestSupported of [true, false]) {
        const mode = selectAttestationMode({ isDev: false, platform, appAttestSupported });
        expect(mode.kind, `${platform}/${appAttestSupported}`).not.toBe("dev-unattested");
      }
    }
  });

  it("uses App Attest on a supporting iPhone in a release build", () => {
    expect(
      selectAttestationMode({ isDev: false, platform: "ios", appAttestSupported: true }),
    ).toEqual({ kind: "app-attest" });
  });

  it("names why a release build cannot attest", () => {
    expect(
      selectAttestationMode({ isDev: false, platform: "ios", appAttestSupported: false }),
    ).toEqual({ kind: "unavailable", reason: "unsupported" });
    // Play Integrity has no server decoder until HB-A3: Android release is
    // refused with its own reason rather than sending something unverifiable
    expect(
      selectAttestationMode({ isDev: false, platform: "android", appAttestSupported: false }),
    ).toEqual({ kind: "unavailable", reason: "pending" });
    expect(
      selectAttestationMode({ isDev: false, platform: "web", appAttestSupported: false }),
    ).toEqual({ kind: "unavailable", reason: "no-platform" });
  });

  it("keeps the dev tier honest about itself in __DEV__ only", () => {
    for (const platform of ["ios", "android"]) {
      expect(selectAttestationMode({ isDev: true, platform, appAttestSupported: true })).toEqual({
        kind: "dev-unattested",
      });
    }
    expect(
      selectAttestationMode({ isDev: true, platform: "web", appAttestSupported: false }).kind,
    ).toBe("unavailable");
  });
});

describe("what goes on the wire", () => {
  it("builds the clientData the server rebuilds, byte for byte", () => {
    expect(attestationClientData("otp.request", "abc")).toBe("intake.attest.v1|otp.request|abc");
    expect(attestationClientData("otp.verify", "abc")).toBe("intake.attest.v1|otp.verify|abc");
    expect(attestationClientData("attest.key", "abc")).toBe("intake.attest.v1|attest.key|abc");
  });

  it("carries an assertion, its key and the challenge in the App Attest header", () => {
    const header = JSON.parse(
      appAttestHeader({ keyId: "a2V5", assertion: "YXNzZXJ0", challenge: "c1", deviceId: "d1" }),
    ) as Record<string, unknown>;
    expect(header).toEqual({
      platform: "ios",
      mode: "app-attest",
      token: "YXNzZXJ0",
      key_id: "a2V5",
      device_id: "d1",
      nonce: "c1",
    });
  });

  it("declares the dev payload for what it is", () => {
    const header = JSON.parse(
      devUnattestedHeader({ platform: "android", deviceId: "d1", challenge: "c1" }),
    ) as Record<string, unknown>;
    expect(header.mode).toBe("dev-unattested");
    expect(header.platform).toBe("android");
    expect(header.nonce).toBe("c1");
    expect(typeof header.token).toBe("string");
  });
});

describe("the stored key slot", () => {
  it("round-trips and refuses anything it did not write", () => {
    const raw = encodeAttestKey({ keyId: "a2V5", registered: true });
    expect(decodeAttestKey(raw)).toEqual({ keyId: "a2V5", registered: true });
    for (const junk of [null, "", "{", "[]", '{"v":2,"keyId":"a","registered":true}', '{"v":1}']) {
      expect(decodeAttestKey(junk), String(junk)).toBeNull();
    }
    expect(
      decodeAttestKey(JSON.stringify({ v: 1, keyId: "x".repeat(65), registered: false })),
    ).toBeNull();
  });
});

describe("failures map to copy, never to server narrative", () => {
  it("maps the native module's error codes", () => {
    expect(nativeFailure("ERR_APP_INTEGRITY_FEATURE_UNSUPPORTED")).toBe("unsupported");
    expect(nativeFailure("ERR_APP_INTEGRITY_SERVER_UNAVAILABLE")).toBe("service");
    expect(nativeFailure("ERR_APP_INTEGRITY_INVALID_KEY")).toBe("invalid-key");
    for (const other of [
      "ERR_APP_INTEGRITY_UNKNOWN",
      "ERR_APP_INTEGRITY_SYSTEM_FAILURE",
      undefined,
      7,
    ]) {
      expect(nativeFailure(other)).toBe("rejected");
    }
  });

  it("gives every failure a tr and en sentence in the siz register, with no numerals", () => {
    const failures = [
      "unsupported",
      "pending",
      "service",
      "rejected",
      "invalid-key",
      null,
    ] as const;
    for (const failure of failures) {
      const key = attestationMessageKey(failure);
      for (const catalogue of [tr, en]) {
        const text = catalogue[key];
        expect(text, key).toBeTruthy();
        expect(text, key).not.toMatch(/[0-9]/);
      }
      expect(tr[key], key).not.toMatch(/\bsen\b|\bsenin\b/i);
    }
    expect(attestationMessageKey("pending")).toBe("auth.error.attestationPending");
    expect(attestationMessageKey("unsupported")).toBe("auth.error.attestationUnsupported");
    expect(attestationMessageKey("service")).toBe("auth.error.attestationService");
    expect(attestationMessageKey("rejected")).toBe("auth.error.attestation");
  });

  it("recognises the server's attestation refusals and nothing else", () => {
    expect(isAttestationRefusal(403, "attestation_unverified")).toBe(true);
    expect(isAttestationRefusal(403, "challenge_invalid")).toBe(true);
    expect(isAttestationRefusal(403, "consent_required")).toBe(false);
    expect(isAttestationRefusal(429, "attestation_unverified")).toBe(false);
  });

  it("re-attests once, and only for a refused App Attest assertion", () => {
    const refused = { status: 403, errorCode: "attestation_unverified" };
    expect(shouldReattest({ ...refused, attempt: 0, mode: "app-attest" })).toBe(true);
    expect(shouldReattest({ ...refused, attempt: 1, mode: "app-attest" })).toBe(false);
    expect(shouldReattest({ ...refused, attempt: 0, mode: "dev-unattested" })).toBe(false);
    expect(
      shouldReattest({
        status: 403,
        errorCode: "challenge_invalid",
        attempt: 0,
        mode: "app-attest",
      }),
    ).toBe(false);
    expect(
      shouldReattest({ status: 429, errorCode: "otp_limited", attempt: 0, mode: "app-attest" }),
    ).toBe(false);
  });
});

// --- the key lifecycle against in-memory ports ------------------------------------------

interface Calls {
  generated: string[];
  attested: { keyId: string; clientData: string }[];
  asserted: { keyId: string; clientData: string }[];
  registered: KeyRegistration[];
  challenges: number;
}

function nativeError(code: string): Error {
  return Object.assign(new Error(code), { code });
}

function world(
  mode: AttestationMode,
  options: {
    refuseRegistration?: boolean;
    invalidKeyOnAssert?: number;
    invalidKeyOnAttest?: number;
    assertError?: string;
    stored?: string | null;
  } = {},
): { ports: AttestationPorts; calls: Calls; slot: { value: string | null } } {
  const calls: Calls = { generated: [], attested: [], asserted: [], registered: [], challenges: 0 };
  const slot = { value: options.stored ?? null };
  let invalidOnAssert = options.invalidKeyOnAssert ?? 0;
  let invalidOnAttest = options.invalidKeyOnAttest ?? 0;
  const ports: AttestationPorts = {
    mode,
    platform: "ios",
    deviceId: async () => "install-a",
    challenge: async () => {
      calls.challenges += 1;
      return `challenge-${calls.challenges}`;
    },
    registerKey: async (body) => {
      calls.registered.push(body);
      if (options.refuseRegistration) {
        throw new AttestationFailureError("rejected");
      }
    },
    store: {
      load: async () => slot.value,
      save: async (raw) => {
        slot.value = raw;
      },
      forget: async () => {
        slot.value = null;
      },
    },
    appAttest: {
      generateKey: async () => {
        const keyId = `key-${calls.generated.length + 1}`;
        calls.generated.push(keyId);
        return keyId;
      },
      attestKey: async (keyId, clientData) => {
        if (invalidOnAttest > 0) {
          invalidOnAttest -= 1;
          throw nativeError("ERR_APP_INTEGRITY_INVALID_KEY");
        }
        calls.attested.push({ keyId, clientData });
        return `attestation-of-${keyId}`;
      },
      generateAssertion: async (keyId, clientData) => {
        if (options.assertError !== undefined) {
          throw nativeError(options.assertError);
        }
        if (invalidOnAssert > 0) {
          invalidOnAssert -= 1;
          throw nativeError("ERR_APP_INTEGRITY_INVALID_KEY");
        }
        calls.asserted.push({ keyId, clientData });
        return `assertion-by-${keyId}`;
      },
    },
  };
  return { ports, calls, slot };
}

async function failureOf(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof AttestationFailureError) {
      return error.failure;
    }
    throw error;
  }
  throw new Error("expected an attestation failure");
}

describe("the App Attest key lifecycle", () => {
  it("registers a key once, then signs each call with an assertion bound to it", async () => {
    const { ports, calls, slot } = world({ kind: "app-attest" });
    const first = JSON.parse(await buildAttestationHeader("otp.request", ports)) as Record<
      string,
      string
    >;

    expect(calls.generated).toEqual(["key-1"]);
    expect(calls.attested).toEqual([
      { keyId: "key-1", clientData: "intake.attest.v1|attest.key|challenge-1" },
    ]);
    expect(calls.registered).toEqual([
      {
        platform: "ios",
        key_id: "key-1",
        attestation: "attestation-of-key-1",
        challenge: "challenge-1",
      },
    ]);
    expect(calls.asserted).toEqual([
      { keyId: "key-1", clientData: "intake.attest.v1|otp.request|challenge-2" },
    ]);
    expect(first).toMatchObject({ mode: "app-attest", key_id: "key-1", nonce: "challenge-2" });
    expect(decodeAttestKey(slot.value)).toEqual({ keyId: "key-1", registered: true });

    const second = JSON.parse(await buildAttestationHeader("otp.verify", ports)) as Record<
      string,
      string
    >;
    expect(calls.generated).toHaveLength(1);
    expect(calls.attested).toHaveLength(1);
    expect(calls.asserted[1]).toEqual({
      keyId: "key-1",
      clientData: "intake.attest.v1|otp.verify|challenge-3",
    });
    expect(second.token).toBe("assertion-by-key-1");
  });

  it("forgets a key the server refused to register, so the next attempt starts clean", async () => {
    const { ports, slot } = world({ kind: "app-attest" }, { refuseRegistration: true });
    expect(await failureOf(buildAttestationHeader("otp.request", ports))).toBe("rejected");
    expect(slot.value).toBeNull();
  });

  it("attests a new key once when the enclave no longer has the stored one", async () => {
    const stored = encodeAttestKey({ keyId: "key-lost", registered: true });
    const { ports, calls, slot } = world({ kind: "app-attest" }, { stored, invalidKeyOnAssert: 1 });
    const header = JSON.parse(await buildAttestationHeader("otp.request", ports)) as Record<
      string,
      string
    >;
    expect(calls.generated).toEqual(["key-1"]);
    expect(header.key_id).toBe("key-1");
    expect(decodeAttestKey(slot.value)).toEqual({ keyId: "key-1", registered: true });
  });

  it("gives up after one fresh key rather than looping", async () => {
    const stored = encodeAttestKey({ keyId: "key-lost", registered: true });
    const { ports } = world({ kind: "app-attest" }, { stored, invalidKeyOnAssert: 2 });
    expect(await failureOf(buildAttestationHeader("otp.request", ports))).toBe("invalid-key");
  });

  it("replaces a stored key the enclave will not attest", async () => {
    const stored = encodeAttestKey({ keyId: "key-half", registered: false });
    const { ports, calls } = world({ kind: "app-attest" }, { stored, invalidKeyOnAttest: 1 });
    await buildAttestationHeader("otp.request", ports);
    expect(calls.generated).toEqual(["key-1"]);
    expect(calls.registered.map((body) => body.key_id)).toEqual(["key-1"]);
  });

  it("surfaces Apple's service being down as its own failure", async () => {
    const { ports } = world(
      { kind: "app-attest" },
      { assertError: "ERR_APP_INTEGRITY_SERVER_UNAVAILABLE" },
    );
    expect(await failureOf(buildAttestationHeader("otp.request", ports))).toBe("service");
  });

  it("refuses before asking for a challenge when the device cannot attest", async () => {
    for (const reason of ["pending", "unsupported", "no-platform"] as const) {
      const { ports, calls } = world({ kind: "unavailable", reason });
      const failure = await failureOf(buildAttestationHeader("otp.request", ports));
      expect(failure).toBe(reason === "pending" ? "pending" : "unsupported");
      expect(calls.challenges).toBe(0);
    }
  });

  it("sends the honest dev payload in __DEV__ and never touches App Attest", async () => {
    const { ports, calls } = world({ kind: "dev-unattested" });
    const header = JSON.parse(await buildAttestationHeader("otp.request", ports)) as Record<
      string,
      string
    >;
    expect(header.mode).toBe("dev-unattested");
    expect(header.nonce).toBe("challenge-1");
    expect(calls.generated).toHaveLength(0);
    expect(calls.asserted).toHaveLength(0);
  });
});
