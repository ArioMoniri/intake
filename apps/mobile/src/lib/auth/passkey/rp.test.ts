/**
 * INT-582 (D36) — the phone refuses WebAuthn options it should not act on.
 *
 * The relying party is D34's domain-bound host, read here from the decision
 * row itself (files/00_STATE.md) rather than restated, so the two cannot
 * drift. Each refusal has its near miss: the well-formed options pass.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { PASSKEY_RP_ID, STEP_UP_ACTIONS, guardCreationOptions, guardStepUpOffer } from "./rp";

const repo = (path: string) => fileURLToPath(new URL(`../../../../../../${path}`, import.meta.url));

function creation(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    publicKey: {
      rp: { id: PASSKEY_RP_ID, name: "Önvizit" },
      user: { id: "aGFuZGxl", name: "Önvizit", displayName: "Önvizit" },
      challenge: "Y2hhbGxlbmdl",
      pubKeyCredParams: [{ type: "public-key", alg: -7 }],
      timeout: 120000,
      excludeCredentials: [],
      authenticatorSelection: {
        authenticatorAttachment: "platform",
        residentKey: "required",
        userVerification: "required",
      },
      attestation: "none",
      ...overrides,
    },
  };
}

function offer(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    enrolled: true,
    publicKey: {
      challenge: "Y2hhbGxlbmdl",
      rpId: PASSKEY_RP_ID,
      allowCredentials: [{ type: "public-key", id: "Y3JlZA" }],
      userVerification: "required",
      timeout: 120000,
      ...overrides,
    },
  };
}

describe("the relying party is D34's domain-bound host", () => {
  it("equals the webcredentials host the owner decided in D34", () => {
    const state = readFileSync(repo("files/00_STATE.md"), "utf8");
    const row = state.split("\n").find((line) => line.startsWith("| **D34**"));
    expect(row).toBeDefined();
    const host = /webcredentials:([a-z0-9.-]+)/.exec(row ?? "")?.[1];
    expect(host).toBe(PASSKEY_RP_ID);
  });

  it("app.json names no other webcredentials host (INT-580 adds this one)", () => {
    const app = JSON.parse(readFileSync(repo("apps/mobile/app.json"), "utf8")) as {
      expo: { ios?: { associatedDomains?: string[] } };
    };
    const hosts = (app.expo.ios?.associatedDomains ?? [])
      .filter((entry) => entry.startsWith("webcredentials:"))
      .map((entry) => entry.slice("webcredentials:".length));
    for (const host of hosts) {
      expect(host).toBe(PASSKEY_RP_ID);
    }
  });

  it("names D36's four actions and the mechanism's own three, and no other", () => {
    expect([...STEP_UP_ACTIONS]).toEqual([
      "doctor_link_issue",
      "phone_change",
      "data_export",
      "data_delete",
      "passkey_add",
      "passkey_remove",
      "recovery_cancel",
    ]);
  });
});

describe("creation options", () => {
  it("passes well-formed options through", () => {
    const guarded = guardCreationOptions(creation());
    expect(guarded?.rp.id).toBe(PASSKEY_RP_ID);
    expect(guarded?.attestation).toBe("none");
  });

  it.each([
    ["another relying party", { rp: { id: "evil.example", name: "x" } }],
    ["the parent domain", { rp: { id: "sslip.io", name: "x" } }],
    ["an attestation", { attestation: "direct" }],
    ["no ES256", { pubKeyCredParams: [{ type: "public-key", alg: -257 }] }],
    ["a challenge that is not base64url", { challenge: "a b" }],
    ["a malformed exclusion", { excludeCredentials: [{ type: "public-key", id: "" }] }],
    [
      "verification only preferred",
      {
        authenticatorSelection: {
          authenticatorAttachment: "platform",
          residentKey: "required",
          userVerification: "preferred",
        },
      },
    ],
    [
      "a roaming authenticator",
      {
        authenticatorSelection: {
          authenticatorAttachment: "cross-platform",
          residentKey: "required",
          userVerification: "required",
        },
      },
    ],
  ])("refuses %s", (_label, overrides) => {
    expect(guardCreationOptions(creation(overrides))).toBeNull();
  });

  it("refuses something that is not options at all", () => {
    expect(guardCreationOptions(null)).toBeNull();
    expect(guardCreationOptions({ publicKey: [] })).toBeNull();
  });
});

describe("the step-up answer", () => {
  it("passes an enrolled answer through", () => {
    const guarded = guardStepUpOffer(offer());
    expect(guarded).toEqual({
      enrolled: true,
      options: {
        challenge: "Y2hhbGxlbmdl",
        rpId: PASSKEY_RP_ID,
        allowCredentials: [{ type: "public-key", id: "Y3JlZA" }],
        userVerification: "required",
        timeout: 120000,
      },
    });
  });

  it("reads 'not enrolled' as the OTP tier with the server's offer", () => {
    expect(
      guardStepUpOffer({ enrolled: false, tier: "otp_session", enrolment: "offered" }),
    ).toEqual({ enrolled: false, enrolment: "offered" });
    expect(
      guardStepUpOffer({ enrolled: false, tier: "otp_session", enrolment: "unavailable" }),
    ).toEqual({ enrolled: false, enrolment: "unavailable" });
    expect(guardStepUpOffer({ enrolled: false, tier: "none" })).toBeNull();
  });

  it.each([
    ["another relying party", { rpId: "evil.example" }],
    ["a malformed credential descriptor", { allowCredentials: [{ type: "public-key", id: "" }] }],
    ["verification only preferred", { userVerification: "preferred" }],
    ["a missing challenge", { challenge: undefined }],
  ])("refuses %s", (_label, overrides) => {
    expect(guardStepUpOffer(offer(overrides))).toBeNull();
  });

  it("refuses something that is not an answer", () => {
    expect(guardStepUpOffer("enrolled")).toBeNull();
    expect(guardStepUpOffer({ enrolled: "yes" })).toBeNull();
  });
});

describe("INT-582 review: no credential id is needed to step up", () => {
  it("an enrolled answer with an empty allowCredentials passes (a discoverable passkey)", () => {
    expect(guardStepUpOffer(offer({ allowCredentials: [] }))).toMatchObject({
      enrolled: true,
      options: { allowCredentials: [] },
    });
  });
});
