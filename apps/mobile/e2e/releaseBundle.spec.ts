/**
 * INT-410 · the production export carries no synthetic seed (audit F30).
 *
 * Acceptance (verbatim): "… a bundle test over the production export proves
 * no seed identifier, name or fixture string is present, with a near-miss
 * control where a planted seed string in a release path fails".
 *
 * This spec builds the release bundle, the way a store build does: Metro with
 * `dev=false` and minification, for iOS and Android, via `expo export` into a
 * temp directory that is removed afterwards and never committed.
 * `--no-bytecode` stops one step short of Hermes, so the emitted file is the
 * JavaScript `hermesc` would compile. Compiling keeps every string, so a
 * string absent here is absent from the bytecode too. It runs in check-ts,
 * the CI job that installs the workspace. Its companion
 * tests/release/test_release_bundle_has_no_fixtures.py checks the release
 * import graph statically in check-py, which has no Node.
 *
 * The markers are the seed's identifying strings: every `id`, `name`,
 * `hospital`, `text` and `title` value in src/lib/dev/accounts.ts. They are
 * read from that file at run time and never spelled here, so the guard is not
 * a second copy of the seed. A seed `department` is deliberately not a marker,
 * because those are the taxonomy's own branch names, which the release app
 * ships. The near miss below pins that.
 *
 * Metro writes non-ASCII characters as `\u` (four hex digits) or `\x` escapes, so the
 * bundle is decoded before it is searched. A marker counts only as a whole
 * string literal.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");
const SEED = join(MOBILE, "src", "lib", "dev", "accounts.ts");
const EXPO = join(MOBILE, "node_modules", ".bin", "expo");

const PLATFORMS = ["ios", "android"] as const;
type Platform = (typeof PLATFORMS)[number];

/** Seed keys whose values identify the seed and nothing else. */
const MARKER_KEYS = ["id", "name", "hospital", "text", "title"];
/** Seed keys whose values are the product's own vocabulary (the branch taxonomy). */
const SHARED_KEYS = ["department"];

/** Every string value the seed module assigns to one of `keys`, sorted. */
function seedValues(keys: readonly string[]): string[] {
  const source = readFileSync(SEED, "utf8");
  const pattern = new RegExp(`\\b(?:${keys.join("|")})\\s*:\\s*"([^"\\\\]+)"`, "g");
  return [...new Set([...source.matchAll(pattern)].map((match) => match[1]))].sort();
}

/** Undo the `\u{…}`, four-digit `\u` and two-digit `\x` escapes a minifier writes. */
function decodeJsEscapes(text: string): string {
  return text.replace(
    /\\u\{([0-9a-fA-F]+)\}|\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})/g,
    (_match, braced?: string, four?: string, two?: string) =>
      String.fromCodePoint(Number.parseInt(braced ?? four ?? two ?? "", 16)),
  );
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The markers that appear in `bundle` as a whole string literal. */
function seedHits(bundle: string, markers: readonly string[]): string[] {
  const decoded = decodeJsEscapes(bundle);
  return markers.filter((marker) => new RegExp(`(["'\`])${escapeRegExp(marker)}\\1`).test(decoded));
}

/** `text` the way Metro's minifier emits a non-ASCII literal. */
function metroEscape(text: string): string {
  return [...text]
    .map((ch) => {
      const code = ch.codePointAt(0) ?? 0;
      return code < 128 ? ch : `\\u${code.toString(16).padStart(4, "0")}`;
    })
    .join("");
}

const markers = seedValues(MARKER_KEYS);
const bundles = {} as Record<Platform, string>;
let out = "";

beforeAll(() => {
  if (!existsSync(EXPO)) {
    throw new Error(
      `${EXPO} is missing: the release bundle can only be built with the workspace installed (pnpm install --frozen-lockfile).`,
    );
  }
  out = mkdtempSync(join(tmpdir(), "intake-release-export-"));
  const args = ["export", "--output-dir", out, "--no-bytecode"];
  for (const platform of PLATFORMS) {
    args.push("--platform", platform);
  }
  try {
    execFileSync(EXPO, args, {
      cwd: MOBILE,
      env: {
        ...process.env,
        CI: "1",
        NODE_ENV: "production",
        EAS_BUILD_PROFILE: "production",
        EXPO_NO_TELEMETRY: "1",
        EXPO_OFFLINE: "1",
      },
      stdio: ["ignore", "pipe", "pipe"],
      maxBuffer: 64 * 1024 * 1024,
    });
  } catch (error) {
    const { stdout, stderr } = error as { stdout?: Buffer; stderr?: Buffer };
    throw new Error(
      `expo export failed:\n${String(stdout ?? "").slice(-3000)}\n${String(stderr ?? "").slice(-3000)}`,
    );
  }
  for (const platform of PLATFORMS) {
    const dir = join(out, "_expo", "static", "js", platform);
    const files = readdirSync(dir).filter((name) => name.endsWith(".js"));
    if (files.length === 0) {
      throw new Error(`the export wrote no ${platform} bundle under ${dir}`);
    }
    bundles[platform] = files.map((name) => readFileSync(join(dir, name), "utf8")).join("\n");
  }
}, 900_000);

afterAll(() => {
  if (out !== "") {
    rmSync(out, { recursive: true, force: true });
  }
});

describe("the production export carries no synthetic seed (INT-410, audit F30)", () => {
  it("derives its markers from the seed, loudly", () => {
    // an empty derivation would pass every bundle
    expect(markers.length).toBeGreaterThanOrEqual(10);
  });

  it.each(PLATFORMS)("%s: no seed identifier, name or fixture string", (platform) => {
    expect(seedHits(bundles[platform], markers)).toEqual([]);
  });

  it.each(PLATFORMS)("%s: the bundle is the real app, not an empty file", (platform) => {
    expect(bundles[platform].length).toBeGreaterThan(1_000_000);
    expect(bundles[platform]).toContain('"welcome.phoneCta"');
  });
});

describe("controls: a seed string planted on a release path is found", () => {
  it("a seed name, escaped as Metro writes it, inside a module factory", () => {
    const [name] = seedValues(["name"]);
    const planted = `${bundles.ios}\n__d(function(g,r,i,a,m,e,d){e.x={name:"${metroEscape(name)}"}},9999,[]);`;
    expect(seedHits(planted, markers)).toEqual([name]);
  });

  it("a seed id as a single-quoted literal", () => {
    const [id] = seedValues(["id"]);
    expect(seedHits(`${bundles.android}\nvar planted='${id}';`, markers)).toEqual([id]);
  });

  it("every marker, each escaped as Metro writes it", () => {
    const planted = markers.map((marker) => `x="${metroEscape(marker)}"`).join(";");
    expect(seedHits(planted, markers)).toEqual(markers);
  });
});

describe("near misses: what is not the seed passes", () => {
  it("a string the seed shares with the product is not a marker, and it ships", () => {
    const shared = seedValues(SHARED_KEYS);
    expect(shared.length).toBeGreaterThan(0);
    expect(shared.filter((value) => markers.includes(value))).toEqual([]);
    const decoded = decodeJsEscapes(bundles.ios);
    expect(shared.some((value) => decoded.includes(`"${value}"`))).toBe(true);
  });

  it("a marker inside a longer word is not a hit", () => {
    // e.g. a short seed id inside a city name: only a whole literal counts
    const padded = markers.map((marker) => `x="k${marker}ri"`).join(";");
    expect(seedHits(padded, markers)).toEqual([]);
  });
});
