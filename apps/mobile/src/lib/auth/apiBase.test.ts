/**
 * INT-328 (audit F01): a release build reaches the API only through a
 * configured https base.
 *
 * `apiBase()` used to walk the Metro hostUri plus `extra.asrHosts` over plain
 * http in every build. A store build has no hostUri, so it probed loopback and
 * a hotspot LAN address, found nothing, and the patient read "sunucuya
 * ulaşılamadı" before they had done anything wrong. The rule these tests hold:
 *
 *   - release (`!__DEV__`): the base comes ONLY from build-time config; it must
 *     be https on a public DNS name; anything else is a typed
 *     `ApiBaseUnconfigured` that the auth screens render as their own copy;
 *   - dev: the LAN walk, exactly as before, and nothing else;
 *   - lib/dev is not reachable from the production call path.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import { serviceCandidates } from "../dev/hosts";
import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import {
  ApiBaseUnconfigured,
  parseReleaseApiBase,
  resolveApiBase,
  type ApiBaseRefusal,
} from "./apiBase";
import { AuthApiError } from "./errors";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "..");
const MOBILE = join(SRC, "..");

function refusalOf(raw: unknown): ApiBaseRefusal | "accepted" {
  try {
    parseReleaseApiBase(raw);
    return "accepted";
  } catch (error) {
    expect(error).toBeInstanceOf(ApiBaseUnconfigured);
    return (error as ApiBaseUnconfigured).reason;
  }
}

function neverCalled(): () => Promise<string | null> {
  return vi.fn(async () => "http://127.0.0.1:8000");
}

// ---------------------------------------------------------------------------
// Release: configured https or a typed refusal
// ---------------------------------------------------------------------------

describe("release build · the API base is the configured https base", () => {
  it("uses a configured https base, and never walks the LAN to find one", async () => {
    const devBase = neverCalled();
    const base = await resolveApiBase({
      isDev: false,
      configured: "https://api.example.org",
      devBase,
    });
    expect(base).toBe("https://api.example.org");
    expect(devBase).not.toHaveBeenCalled();
  });

  it("keeps a port and a path prefix, and drops a trailing slash", () => {
    expect(parseReleaseApiBase("https://api.example.org:8443/intake/")).toBe(
      "https://api.example.org:8443/intake",
    );
    expect(parseReleaseApiBase("  https://api.example.org/  ")).toBe("https://api.example.org");
  });

  // one-element rows: a bare array row would be spread into the arguments
  it.each([[undefined], [null], [""], ["   "], [42], [{}], [[]]])(
    "unset (%j) is ApiBaseUnconfigured, never a guessed host",
    async (configured) => {
      const devBase = neverCalled();
      const attempt = resolveApiBase({ isDev: false, configured, devBase });
      await expect(attempt).rejects.toBeInstanceOf(ApiBaseUnconfigured);
      await expect(attempt).rejects.toMatchObject({ kind: "unconfigured", reason: "unset" });
      expect(devBase).not.toHaveBeenCalled();
    },
  );

  it.each([
    "http://api.example.org",
    "HTTP://api.example.org",
    "ws://api.example.org",
    "ftp://api.example.org",
  ])("a non-https scheme (%s) is refused as insecure", (configured) => {
    expect(refusalOf(configured)).toBe("insecure");
  });

  it.each([
    "api.example.org",
    "https://",
    "https:///v1",
    "https://api.example.org?x=1",
    "https://api.example.org#frag",
    "https://user@api.example.org",
    "https://api example.org",
    "https://api.example.org:0",
    "https://api.example.org:70000",
    "https://-api.example.org",
  ])("a malformed value (%s) is refused", (configured) => {
    expect(refusalOf(configured)).toBe("malformed");
  });

  it.each([
    "https://localhost",
    "https://localhost:8000",
    "https://127.0.0.1:8000",
    "https://172.20.10.3:8000",
    "https://192.168.1.20",
    "https://10.0.0.5",
    "https://[::1]:8000",
    "https://mac.local",
    "https://api.localhost",
    "https://intranet",
  ])("a loopback, LAN or single-label host (%s) is refused", (configured) => {
    expect(refusalOf(configured)).toBe("not_public");
  });

  it("the refusal is an AuthApiError, so every existing catch still sees it", () => {
    let caught: unknown = null;
    try {
      parseReleaseApiBase("");
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(AuthApiError);
    expect((caught as AuthApiError).kind).toBe("unconfigured");
    // codes, never narrative — and never the configured value itself
    expect((caught as AuthApiError).message).toBe("unconfigured");
  });

  it("never returns a hostUri or asrHosts candidate, from the real app.json", async () => {
    const app = JSON.parse(readFileSync(join(MOBILE, "app.json"), "utf8")) as {
      expo: { extra: { asrHosts: string[] } };
    };
    const lan = serviceCandidates("192.168.1.20:8081", app.expo.extra.asrHosts, 8000);
    expect(lan.length).toBeGreaterThan(1);
    for (const candidate of lan) {
      expect(refusalOf(candidate)).toBe("insecure");
      expect(refusalOf(candidate.replace(/^http:/, "https:"))).toBe("not_public");
      const devBase = vi.fn(async () => candidate);
      await expect(
        resolveApiBase({ isDev: false, configured: undefined, devBase }),
      ).rejects.toBeInstanceOf(ApiBaseUnconfigured);
      expect(devBase).not.toHaveBeenCalled();
    }
  });
});

// ---------------------------------------------------------------------------
// Dev: the LAN walk, unchanged
// ---------------------------------------------------------------------------

describe("dev build · the LAN walk is exactly as before", () => {
  it("returns whatever the dev walk finds", async () => {
    const devBase = vi.fn(async () => "http://172.20.10.3:8000");
    expect(await resolveApiBase({ isDev: true, configured: undefined, devBase })).toBe(
      "http://172.20.10.3:8000",
    );
    expect(devBase).toHaveBeenCalledTimes(1);
  });

  it("passes the walk's null through, so each caller keeps its own miss", async () => {
    const devBase = vi.fn(async () => null);
    expect(await resolveApiBase({ isDev: true, configured: undefined, devBase })).toBeNull();
  });

  it("ignores a configured release base, even an https one", async () => {
    const devBase = vi.fn(async () => "http://127.0.0.1:8000");
    expect(
      await resolveApiBase({ isDev: true, configured: "https://api.example.org", devBase }),
    ).toBe("http://127.0.0.1:8000");
  });
});

// ---------------------------------------------------------------------------
// The UI renders the refusal as its own Turkish state
// ---------------------------------------------------------------------------

describe("the unconfigured state reaches the patient as tr copy", () => {
  it("has a tr source string and an en mirror, numeral-free", () => {
    const trCopy = (tr as Record<string, string>)["auth.error.unconfigured"];
    const enCopy = (en as Record<string, string>)["auth.error.unconfigured"];
    expect(trCopy).toBeTruthy();
    expect(enCopy).toBeTruthy();
    expect(trCopy).not.toBe(tr["auth.error.network"]);
    expect(trCopy).not.toMatch(/\d/);
    expect(enCopy).not.toMatch(/\d/);
  });

  it.each(["phone.tsx", "otp.tsx"])("(auth)/%s maps the unconfigured kind to that copy", (file) => {
    const screen = readFileSync(join(SRC, "app", "(auth)", file), "utf8");
    expect(screen).toMatch(/case "unconfigured":\s*return "auth\.error\.unconfigured";/);
  });
});

// ---------------------------------------------------------------------------
// lib/dev is not on the production call path
// ---------------------------------------------------------------------------

/**
 * The static import graph, the same walk ttsLane.test.ts uses for the RED
 * path. `import type` is skipped because the compiler erases it; a dynamic
 * `import()` is not followed because it is not a static edge — the one the
 * Expo binding owns is checked separately, below, to sit behind the dev branch.
 */
function resolveImport(fromFile: string, specifier: string): string | null {
  let base: string;
  if (specifier.startsWith("@/")) {
    base = join(SRC, specifier.slice(2));
  } else if (specifier.startsWith(".")) {
    base = resolve(dirname(fromFile), specifier);
  } else {
    return null; // a package, not our tree
  }
  for (const candidate of [
    `${base}.ts`,
    `${base}.tsx`,
    join(base, "index.ts"),
    join(base, "index.tsx"),
  ]) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

const STATIC_EDGE = /^\s*(?:import|export)\s+(?!type\b)(?:[^;"]*?\s+from\s+)?"([^"]+)"/gm;

function reachableFrom(entry: string): Set<string> {
  const seen = new Set<string>();
  const queue = [entry];
  while (queue.length > 0) {
    const file = queue.pop() as string;
    if (seen.has(file)) {
      continue;
    }
    seen.add(file);
    for (const match of readFileSync(file, "utf8").matchAll(STATIC_EDGE)) {
      const target = resolveImport(file, match[1]);
      if (target !== null) {
        queue.push(target);
      }
    }
  }
  return seen;
}

const DEV_DIR = `${sep}lib${sep}dev${sep}`;

describe("lib/dev is not reachable from the production call path", () => {
  it("the auth client's static import graph holds no lib/dev module", () => {
    const reached = [...reachableFrom(join(SRC, "lib", "auth", "api.ts"))];
    // not vacuous: the walk really does reach the resolver and its neighbours
    expect(reached.some((file) => file.endsWith(`${sep}auth${sep}apiBase.ts`))).toBe(true);
    expect(reached.some((file) => file.endsWith(`${sep}auth${sep}expoApiBase.ts`))).toBe(true);
    expect(reached.some((file) => file.endsWith(`${sep}auth${sep}tokens.ts`))).toBe(true);
    expect(reached.filter((file) => file.includes(DEV_DIR))).toEqual([]);
  });

  it("the pure resolver reaches nothing but the typed errors", () => {
    const reached = [...reachableFrom(join(SRC, "lib", "auth", "apiBase.ts"))].map((file) =>
      file.slice(SRC.length + 1),
    );
    expect(reached.sort()).toEqual(
      [join("lib", "auth", "apiBase.ts"), join("lib", "auth", "errors.ts")].sort(),
    );
  });

  it("the Expo binding touches lib/dev only through a lazy import on the dev branch", () => {
    const source = readFileSync(join(SRC, "lib", "auth", "expoApiBase.ts"), "utf8");
    const devSpecifiers = [...source.matchAll(/"([^"]*\/dev\/[^"]*)"/g)].map((m) => m[1]);
    expect(devSpecifiers).toEqual(["../dev/expoHosts"]);
    expect(source).toContain('await import("../dev/expoHosts")');
    // the walk is handed to the resolver, which calls it only when isDev
    expect(source).toMatch(/isDev:\s*__DEV__/);
  });

  it("clips resolve the dev George base through the same resolver, not a second LAN walk", () => {
    const clips = readFileSync(join(SRC, "lib", "dialogue", "clips.ts"), "utf8");
    expect(clips).toContain('from "../auth/expoApiBase"');
    expect(clips).not.toContain("configuredServiceCandidates");
    expect(clips).not.toContain("/healthz");
  });

  it("the auth client names no LAN walk of its own", () => {
    const api = readFileSync(join(SRC, "lib", "auth", "api.ts"), "utf8");
    expect(api).not.toContain("configuredServiceCandidates");
    expect(api).not.toMatch(/lib\/dev\//);
  });
});
