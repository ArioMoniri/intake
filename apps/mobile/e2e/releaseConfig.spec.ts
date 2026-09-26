/**
 * INT-328 release config (audit F01 + F17 + F29), pinned as config facts.
 *
 * - F01: the release API base is BUILD-TIME config. `app.config.ts` copies the
 *   EAS environment variable `EXPO_PUBLIC_API_BASE_URL` into
 *   `extra.apiBaseUrl`, and nothing else ever fills it. No hostname is
 *   committed: the production FQDN is a human decision (HB-I14), so until it is
 *   set the value is empty and the app fails closed (lib/auth/apiBase.ts).
 * - F17: the store build must not raise the iOS local-network prompt, so the
 *   production profile never declares `NSLocalNetworkUsageDescription` (nor the
 *   Bonjour list that goes with it), whatever app.json says.
 * - F29: `extra.asrHosts` / `extra.ttsLanes` are sets in all but type; a
 *   duplicate only doubles the dev probe walk, so the resolved config holds
 *   each entry once, in first-seen order.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { ConfigContext, ExpoConfig } from "expo/config";
import { afterEach, describe, expect, it, vi } from "vitest";

import appConfig, { API_BASE_ENV, resolveAppConfig } from "../app.config";

const ROOT = join(__dirname, "..");

function appJson(): ExpoConfig {
  return (JSON.parse(readFileSync(join(ROOT, "app.json"), "utf8")) as { expo: ExpoConfig }).expo;
}

const PRODUCTION = { EAS_BUILD_PROFILE: "production" };
const LOCAL_NETWORK_PLIST = {
  NSLocalNetworkUsageDescription: "yerel ağ",
  NSBonjourServices: ["_expo._tcp"],
  NSMicrophoneUsageDescription: "mikrofon",
};

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("F01 · the release API base is build-time config, never a committed host", () => {
  it("names the EAS variable the owner sets", () => {
    expect(API_BASE_ENV).toBe("EXPO_PUBLIC_API_BASE_URL");
  });

  it("copies the EAS variable into extra.apiBaseUrl", () => {
    const resolved = resolveAppConfig(appJson(), {
      ...PRODUCTION,
      EXPO_PUBLIC_API_BASE_URL: " https://api.example.org ",
    });
    expect(resolved.extra?.apiBaseUrl).toBe("https://api.example.org");
  });

  it("is empty until someone sets it — the app then fails closed", () => {
    expect(resolveAppConfig(appJson(), PRODUCTION).extra?.apiBaseUrl).toBe("");
    expect(resolveAppConfig(appJson(), {}).extra?.apiBaseUrl).toBe("");
  });

  it("the environment is the only source: app.json cannot smuggle a host in", () => {
    const withHost = {
      ...appJson(),
      extra: { ...appJson().extra, apiBaseUrl: "https://x.example" },
    };
    expect(resolveAppConfig(withHost, PRODUCTION).extra?.apiBaseUrl).toBe("");
    expect(JSON.stringify(appJson())).not.toContain("apiBaseUrl");
  });

  it("the default export reads the real process environment", () => {
    vi.stubEnv(API_BASE_ENV, "https://api.example.org");
    const resolved = appConfig({ config: appJson() } as ConfigContext);
    expect(resolved.extra?.apiBaseUrl).toBe("https://api.example.org");
    expect(resolved.name).toBe(appJson().name);
  });

  it("keeps every other extra value as app.json has it", () => {
    const resolved = resolveAppConfig(appJson(), PRODUCTION);
    expect(resolved.extra?.certificatePins).toEqual(appJson().extra?.certificatePins);
    expect(resolved.extra?.glitchtipDsn).toBe(appJson().extra?.glitchtipDsn);
  });
});

describe("F17 · the production profile raises no local-network prompt", () => {
  it("app.json as committed resolves with no local-network key for production", () => {
    const plist = resolveAppConfig(appJson(), PRODUCTION).ios?.infoPlist ?? {};
    expect(plist).not.toHaveProperty("NSLocalNetworkUsageDescription");
    expect(plist).not.toHaveProperty("NSBonjourServices");
  });

  it("strips a declared local-network key from the production profile, and only it", () => {
    const declared = { ...appJson(), ios: { ...appJson().ios, infoPlist: LOCAL_NETWORK_PLIST } };
    const plist = resolveAppConfig(declared, PRODUCTION).ios?.infoPlist ?? {};
    expect(plist).not.toHaveProperty("NSLocalNetworkUsageDescription");
    expect(plist).not.toHaveProperty("NSBonjourServices");
    expect(plist).toHaveProperty("NSMicrophoneUsageDescription", "mikrofon");
  });

  it.each([{}, { EAS_BUILD_PROFILE: "development" }, { EAS_BUILD_PROFILE: "preview" }])(
    "leaves a non-production profile (%j) exactly as declared",
    (env) => {
      const declared = { ...appJson(), ios: { ...appJson().ios, infoPlist: LOCAL_NETWORK_PLIST } };
      expect(resolveAppConfig(declared, env).ios?.infoPlist).toEqual(LOCAL_NETWORK_PLIST);
    },
  );
});

describe("F29 · the dev host and TTS lane lists hold each entry once", () => {
  it("app.json as committed has no duplicate", () => {
    const extra = appJson().extra as {
      asrHosts: string[];
      ttsLanes: { id: string; port: number }[];
    };
    expect(new Set(extra.asrHosts).size).toBe(extra.asrHosts.length);
    const lanes = extra.ttsLanes.map((lane) => `${lane.id}@${lane.port}`);
    expect(new Set(lanes).size).toBe(lanes.length);
  });

  it("the resolved config collapses duplicates, first-seen order kept", () => {
    const doubled = {
      ...appJson(),
      extra: {
        ...appJson().extra,
        asrHosts: ["127.0.0.1", "172.20.10.3", "127.0.0.1", "172.20.10.3"],
        ttsLanes: [
          { id: "voxcpm2", port: 8805 },
          { id: "freya", port: 8803 },
          { id: "voxcpm2", port: 8805 },
          { id: "freya", port: 8803 },
        ],
      },
    };
    const extra = resolveAppConfig(doubled, {}).extra ?? {};
    expect(extra.asrHosts).toEqual(["127.0.0.1", "172.20.10.3"]);
    expect(extra.ttsLanes).toEqual([
      { id: "voxcpm2", port: 8805 },
      { id: "freya", port: 8803 },
    ]);
  });
});
