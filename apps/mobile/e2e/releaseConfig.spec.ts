/**
 * Release config (INT-328 audit F01 + F17 + F29, INT-421), pinned as config
 * facts.
 *
 * - F01: the release API base is BUILD-TIME config. `app.config.ts` copies the
 *   EAS environment variable `EXPO_PUBLIC_API_BASE_URL` into
 *   `extra.apiBaseUrl`, and nothing else ever fills it: app.json cannot. The
 *   one committed value is eas.json's production profile, a reviewed diff
 *   that EAS Build exports into that environment, and it must pass the same
 *   release parser the app runs (lib/auth/apiBase.ts). HB-I14, the final
 *   FQDN, stays open; with the variable unset the value is empty and the app
 *   fails closed.
 * - F17: the store build must not raise the iOS local-network prompt, so the
 *   production profile never declares `NSLocalNetworkUsageDescription` (nor the
 *   Bonjour list that goes with it), whatever app.json says.
 * - F29: `extra.asrHosts` / `extra.ttsLanes` are sets in all but type; a
 *   duplicate only doubles the dev probe walk, so the resolved config holds
 *   each entry once, in first-seen order.
 * - INT-421: the production profile carries no dev-only lane. The LAN and
 *   loopback voice hosts resolve to empty lists there, and every other profile
 *   keeps them. eas.json commits no signing or submission credential, and the
 *   George dev clip route stays unreachable in a release build. app.json
 *   carries the store identity INT-420 does not own: the Android package, the
 *   export-compliance answer and the owner's EAS project.
 * - INT-491: the orb's body is build-time config too. `app.config.ts` copies
 *   `EXPO_PUBLIC_ORB_VARIANT` into `extra.orbVariant`. Empty is the lens, the
 *   orb ADR-039 names since the owner's "orb=lens" (16 Oct 2026); a
 *   development or preview build may name `classic`, the earlier sphere. The
 *   production profile never carries a value, so a store build draws the lens.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join, sep } from "node:path";

import type { ConfigContext, ExpoConfig } from "expo/config";
import { afterEach, describe, expect, it, vi } from "vitest";

import appConfig, { API_BASE_ENV, ORB_VARIANT_ENV, resolveAppConfig } from "../app.config";
import { ApiBaseUnconfigured, parseReleaseApiBase } from "../src/lib/auth/apiBase";

const ROOT = join(__dirname, "..");
const REPO = join(ROOT, "..", "..");

function appJson(): ExpoConfig {
  return (JSON.parse(readFileSync(join(ROOT, "app.json"), "utf8")) as { expo: ExpoConfig }).expo;
}

interface EasBuildProfile {
  developmentClient?: boolean;
  distribution?: string;
  autoIncrement?: boolean;
  environment?: string;
  env?: Record<string, string>;
  android?: { buildType?: string };
}

interface EasJson {
  cli: { version: string; appVersionSource: string };
  build: Record<string, EasBuildProfile>;
  submit: Record<string, { ios?: Record<string, unknown>; android?: Record<string, unknown> }>;
}

function easJson(): EasJson {
  return JSON.parse(readFileSync(join(ROOT, "eas.json"), "utf8")) as EasJson;
}

/** The production build's committed API base, unvalidated. */
function productionApiBase(): string {
  return easJson().build.production?.env?.[API_BASE_ENV] ?? "";
}

/** Keys that name a signing or submission credential. They stay on the owner's
 * machine or on EAS servers, never in the repository. */
const CREDENTIAL_KEYS = [
  "ascApiKeyPath",
  "ascApiKeyId",
  "ascApiKeyIssuerId",
  "serviceAccountKeyPath",
];
const CREDENTIAL_SHAPE = /key(?:path|id)|issuer|serviceaccount|password|secret|token|credential/i;

/** Every object key in `value`, at any depth, as a dotted path. */
function keyPaths(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) {
    return [];
  }
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix === "" ? key : `${prefix}.${key}`;
    return [path, ...keyPaths(child, path)];
  });
}

/** The committed key paths that look like a credential. */
function credentialPaths(value: unknown): string[] {
  return keyPaths(value).filter((path) => {
    const leaf = path.slice(path.lastIndexOf(".") + 1);
    return CREDENTIAL_KEYS.includes(leaf) || CREDENTIAL_SHAPE.test(leaf);
  });
}

const stripComments = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

/** The body of `function <name>(…) {…}` in `source`, braces balanced, or null. */
function functionBody(source: string, name: string): string | null {
  const start = source.indexOf(`function ${name}(`);
  if (start === -1) {
    return null;
  }
  const open = source.indexOf("{", source.indexOf(")", start));
  let depth = 1;
  let index = open + 1;
  while (depth > 0 && index < source.length) {
    if (source[index] === "{") {
      depth += 1;
    } else if (source[index] === "}") {
      depth -= 1;
    }
    index += 1;
  }
  return source.slice(open, index);
}

const occurrences = (text: string, needle: string): number => text.split(needle).length - 1;

/**
 * Whether the clips module keeps the George dev route behind the real
 * `__DEV__`: the source function returns null before anything else when
 * `__DEV__` is false, it is the only place that fetches a George clip, and the
 * store takes the self-hosted lane alone when it gets null. A release build
 * compiles `__DEV__` to false, so the route is never dialled.
 */
function georgeRouteIsDevOnly(clipsSource: string): boolean {
  const code = stripComments(clipsSource);
  const source = functionBody(code, "createGeorgeSource");
  const store = functionBody(code, "dialogueClipStore");
  if (source === null || store === null) {
    return false;
  }
  const guardFirst = /^\{\s*if \(!__DEV__\) \{\s*return null;\s*\}/.test(source);
  const fetchesOnlyThere =
    occurrences(source, "fetchGeorgeClip(") === 1 && occurrences(code, "fetchGeorgeClip(") === 1;
  const calls = [...code.matchAll(/(?<!function )\bcreateGeorgeSource\(\)/g)].length;
  const builtOnce =
    calls === 1 &&
    /const george = createGeorgeSource\(\);\s*if \(george === null\) \{\s*return createClipStore\([^;]*\bselfHosted\);\s*\}/.test(
      store,
    );
  return guardFirst && fetchesOnlyThere && builtOnce;
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

describe("INT-421 · the production profile carries no dev-only lane", () => {
  it("app.json still declares the dev lanes, so the strip below is not vacuous", () => {
    const extra = appJson().extra as { asrHosts: unknown[]; ttsLanes: unknown[] };
    expect(extra.asrHosts.length).toBeGreaterThan(0);
    expect(extra.ttsLanes.length).toBeGreaterThan(0);
  });

  it("production resolves extra.asrHosts and extra.ttsLanes to empty lists", () => {
    const extra = resolveAppConfig(appJson(), PRODUCTION).extra ?? {};
    expect(extra.asrHosts).toEqual([]);
    expect(extra.ttsLanes).toEqual([]);
  });

  it("production strips a doubled declaration too, not only the committed one", () => {
    const doubled = {
      ...appJson(),
      extra: {
        ...appJson().extra,
        asrHosts: ["127.0.0.1", "127.0.0.1"],
        ttsLanes: [{ id: "freya", port: 8803 }],
      },
    };
    const extra = resolveAppConfig(doubled, PRODUCTION).extra ?? {};
    expect(extra.asrHosts).toEqual([]);
    expect(extra.ttsLanes).toEqual([]);
  });

  it("production keeps every other extra value", () => {
    const extra = resolveAppConfig(appJson(), PRODUCTION).extra ?? {};
    expect(extra.certificatePins).toEqual(appJson().extra?.certificatePins);
    expect(extra.glitchtipDsn).toBe(appJson().extra?.glitchtipDsn);
    expect(extra.eas).toEqual(appJson().extra?.eas);
  });

  it.each([{}, { EAS_BUILD_PROFILE: "development" }, { EAS_BUILD_PROFILE: "preview" }])(
    "near miss: a non-production profile (%j) keeps both lists as app.json declares them",
    (env) => {
      const extra = resolveAppConfig(appJson(), env).extra ?? {};
      expect(extra.asrHosts).toEqual(appJson().extra?.asrHosts);
      expect(extra.ttsLanes).toEqual(appJson().extra?.ttsLanes);
      expect(extra.asrHosts).not.toEqual([]);
    },
  );
});

describe("INT-421 · eas.json is the reviewed release profile", () => {
  it("pins the owner's CLI floor and remote app versioning", () => {
    expect(easJson().cli).toEqual({ version: ">= 24.7.0", appVersionSource: "remote" });
  });

  it("development is an internal dev client and preview is internal", () => {
    const { development, preview } = easJson().build;
    expect(development).toEqual({ developmentClient: true, distribution: "internal" });
    expect(preview).toEqual({ distribution: "internal" });
  });

  it("production auto-increments, reads the production environment and ships an app bundle", () => {
    const production = easJson().build.production;
    expect(production?.autoIncrement).toBe(true);
    expect(production?.environment).toBe("production");
    expect(production?.android?.buildType).toBe("app-bundle");
    expect(production?.developmentClient).toBeUndefined();
  });

  it("the production API base passes the release parser unchanged", () => {
    const base = productionApiBase();
    expect(base).not.toBe("");
    expect(parseReleaseApiBase(base)).toBe(base);
  });

  it("app.config.ts carries that base into the production build", () => {
    const env = { ...PRODUCTION, ...easJson().build.production?.env };
    expect(resolveAppConfig(appJson(), env).extra?.apiBaseUrl).toBe(productionApiBase());
  });

  it("near miss: the same host over http is refused as insecure", () => {
    const insecure = productionApiBase().replace(/^https:/, "http:");
    expect(insecure.startsWith("http://")).toBe(true);
    expect(() => parseReleaseApiBase(insecure)).toThrow(ApiBaseUnconfigured);
    try {
      parseReleaseApiBase(insecure);
    } catch (error) {
      expect((error as ApiBaseUnconfigured).reason).toBe("insecure");
    }
  });

  it("every committed build variable is EXPO_PUBLIC_, public by construction", () => {
    const names = Object.values(easJson().build).flatMap((profile) =>
      Object.keys(profile.env ?? {}),
    );
    expect(names).toContain(API_BASE_ENV);
    expect(names.filter((name) => !name.startsWith("EXPO_PUBLIC_"))).toEqual([]);
  });

  it("submits production to the owner's App Store Connect app and the internal Play track", () => {
    const production = easJson().submit.production;
    expect(production?.ios).toEqual({ ascAppId: "6814005465" });
    expect(production?.android).toEqual({ track: "internal" });
  });

  it("no profile carries a key path, key id, issuer id or service-account path", () => {
    expect(credentialPaths(easJson())).toEqual([]);
  });

  it("control: a planted credential key is found, at any depth", () => {
    const planted = easJson();
    const ios = { ...planted.submit.production?.ios, ascApiKeyIssuerId: "x" };
    const android = { ...planted.submit.production?.android, serviceAccountKeyPath: "x" };
    planted.submit = { ...planted.submit, production: { ios, android } };
    expect(credentialPaths(planted).sort()).toEqual([
      "submit.production.android.serviceAccountKeyPath",
      "submit.production.ios.ascApiKeyIssuerId",
    ]);
    expect(credentialPaths({ submit: { production: { ios: { ascApiKeyPath: "x" } } } })).toEqual([
      "submit.production.ios.ascApiKeyPath",
    ]);
    expect(credentialPaths({ a: { ascApiKeyId: "x" } })).toEqual(["a.ascApiKeyId"]);
  });

  it("near miss: the public App Store Connect app id is not a credential", () => {
    expect(credentialPaths({ submit: { production: { ios: { ascAppId: "1" } } } })).toEqual([]);
  });
});

describe("INT-421 · the George dev clip route is unreachable in a release build", () => {
  const clips = readFileSync(join(ROOT, "src", "lib", "dialogue", "clips.ts"), "utf8");

  it("createGeorgeSource returns null first when __DEV__ is false, and is the only caller", () => {
    expect(georgeRouteIsDevOnly(clips)).toBe(true);
  });

  it("nothing else the app ships reaches the route", () => {
    const shipped = readdirSync(join(ROOT, "src"), { recursive: true, encoding: "utf8" })
      .filter((path) => /\.tsx?$/.test(path) && !path.includes(".test."))
      .map((path) => path.split(sep).join("/"));
    // not vacuous: the walk really does see the dialogue modules
    expect(shipped).toContain("lib/dialogue/clips.ts");
    const reaching = shipped.filter((path) => {
      const code = stripComments(readFileSync(join(ROOT, "src", path), "utf8"));
      return code.includes("fetchGeorgeClip") || code.includes("GEORGE_CLIP_PATH");
    });
    expect(reaching.sort()).toEqual(["lib/dialogue/clips.ts", "lib/dialogue/georgeClip.ts"]);
  });

  it("control: the same module without the guard is caught", () => {
    const unguarded = clips.replace(/if \(!__DEV__\) \{\s*return null;\s*\}/, "");
    expect(unguarded).not.toBe(clips);
    expect(georgeRouteIsDevOnly(unguarded)).toBe(false);
  });

  it("control: a literal in place of __DEV__ is caught", () => {
    const literal = clips.replace("if (!__DEV__) {", "if (!true) {");
    expect(literal).not.toBe(clips);
    expect(georgeRouteIsDevOnly(literal)).toBe(false);
  });

  it("control: a second George fetch outside the guarded source is caught", () => {
    const second = `${clips}\nexport const leak = (b: string, t: ScriptedTr) => fetchGeorgeClip(b, t);\n`;
    expect(georgeRouteIsDevOnly(second)).toBe(false);
  });

  it("near miss: the guard named only in a comment is not a guard", () => {
    const commented = clips.replace("if (!__DEV__) {", "// if (!__DEV__) {\n  {");
    expect(georgeRouteIsDevOnly(commented)).toBe(false);
  });
});

describe("INT-421 · the store identity app.json carries", () => {
  it("the Android package is the identity the API pins for iOS", () => {
    const settings = readFileSync(
      join(REPO, "services", "api", "src", "intake_api", "settings.py"),
      "utf8",
    );
    const pinned = /^IOS_BUNDLE_ID = "([^"]+)"$/m.exec(settings)?.[1];
    expect(pinned).toBe("com.ariomoniri.intakemobile");
    expect(appJson().android?.package).toBe(pinned);
  });

  it("answers export compliance, and the production resolve keeps the answer", () => {
    expect(appJson().ios?.infoPlist?.ITSAppUsesNonExemptEncryption).toBe(false);
    const plist = resolveAppConfig(appJson(), PRODUCTION).ios?.infoPlist ?? {};
    expect(plist).toHaveProperty("ITSAppUsesNonExemptEncryption", false);
  });

  it("names the owner's EAS project", () => {
    expect(appJson().extra?.eas).toEqual({ projectId: "307d4cf2-c447-4855-8110-da59fb5ed170" });
  });

  it("near miss: no foreground-service permission, which served only the dev George demo", () => {
    const permissions = appJson().android?.permissions ?? [];
    expect(permissions.length).toBeGreaterThan(0);
    expect(permissions.filter((name) => name.includes("FOREGROUND_SERVICE"))).toEqual([]);
  });
});

describe("INT-491 · the orb is the lens; the flag only lets a development build name the sphere", () => {
  it("names the variable a development build sets", () => {
    expect(ORB_VARIANT_ENV).toBe("EXPO_PUBLIC_ORB_VARIANT");
  });

  it("is empty when unset: the app draws the lens, the orb ADR-039 now names", () => {
    expect(resolveAppConfig(appJson(), {}).extra?.orbVariant).toBe("");
    expect(JSON.stringify(appJson())).not.toContain("orbVariant");
  });

  it("a development or preview build may name the earlier sphere", () => {
    expect(
      resolveAppConfig(appJson(), { EXPO_PUBLIC_ORB_VARIANT: " classic " }).extra?.orbVariant,
    ).toBe("classic");
    expect(
      resolveAppConfig(appJson(), {
        EAS_BUILD_PROFILE: "preview",
        EXPO_PUBLIC_ORB_VARIANT: "classic",
      }).extra?.orbVariant,
    ).toBe("classic");
  });

  it("the production profile never carries a value, so a store build always draws the lens", () => {
    expect(
      resolveAppConfig(appJson(), { ...PRODUCTION, EXPO_PUBLIC_ORB_VARIANT: "classic" }).extra
        ?.orbVariant,
    ).toBe("");
    const smuggled = { ...appJson(), extra: { ...appJson().extra, orbVariant: "classic" } };
    expect(resolveAppConfig(smuggled, PRODUCTION).extra?.orbVariant).toBe("");
    // Near miss: the same environment outside production is honoured.
    expect(
      resolveAppConfig(appJson(), { EXPO_PUBLIC_ORB_VARIANT: "classic" }).extra?.orbVariant,
    ).toBe("classic");
  });

  it("the environment is the only source: app.json cannot switch the body", () => {
    const smuggled = { ...appJson(), extra: { ...appJson().extra, orbVariant: "classic" } };
    expect(resolveAppConfig(smuggled, {}).extra?.orbVariant).toBe("");
  });
});
