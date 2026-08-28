import { describe, expect, it } from "vitest";

import { healthConsentOn, selectConnectorKind } from "./capability";

describe("selectConnectorKind — the honest capability matrix (INT-200)", () => {
  it("Expo Go resolves to the stub on both platforms (native modules cannot load there)", () => {
    expect(selectConnectorKind({ os: "ios", executionEnvironment: "storeClient" })).toBe(
      "expo_go_stub",
    );
    expect(selectConnectorKind({ os: "android", executionEnvironment: "storeClient" })).toBe(
      "expo_go_stub",
    );
  });

  it("a development/standalone build routes to the platform connector", () => {
    expect(selectConnectorKind({ os: "ios", executionEnvironment: "bare" })).toBe("healthkit");
    expect(selectConnectorKind({ os: "ios", executionEnvironment: "standalone" })).toBe(
      "healthkit",
    );
    expect(selectConnectorKind({ os: "android", executionEnvironment: "bare" })).toBe(
      "health_connect",
    );
    expect(selectConnectorKind({ os: "android", executionEnvironment: "standalone" })).toBe(
      "health_connect",
    );
  });

  it("web and anything unknown is platform_unsupported — never a dead button", () => {
    expect(selectConnectorKind({ os: "web", executionEnvironment: "bare" })).toBe("unsupported");
    expect(selectConnectorKind({ os: "windows", executionEnvironment: "bare" })).toBe(
      "unsupported",
    );
  });
});

describe("healthConsentOn — the section gate (device-local consent, INT-200)", () => {
  it("is off signed out and off until the patient turns it on", () => {
    expect(healthConsentOn(null)).toBe(false);
    expect(
      healthConsentOn({
        core: true,
        voice: true,
        wellbeing: true,
        documents: true,
        health: false,
      }),
    ).toBe(false);
  });

  it("is on only with the explicit health consent", () => {
    expect(
      healthConsentOn({
        core: true,
        voice: false,
        wellbeing: false,
        documents: false,
        health: true,
      }),
    ).toBe(true);
  });
});
