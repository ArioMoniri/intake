/**
 * Navigation-map acceptance (INT-130): the file-system route tree IS the nav
 * map from 02 §4, so this spec pins it structurally — a route renamed or
 * dropped fails here before any device test would notice. It also pins three
 * design invariants that are cheap to enforce as source facts: the wellbeing
 * gate goes through `visibleTabs`, the dev accounts stay behind `__DEV__`,
 * and the emergency colour never leaks outside the theme (02 §5.3 — RED is
 * the route's colour, not a UI accent).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const APP = join(__dirname, "..", "src", "app");
const SRC = join(__dirname, "..", "src");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

// 02 §4 — every route the shell must serve.
const NAV_MAP = [
  "_layout.tsx",
  "index.tsx",
  "(auth)/_layout.tsx",
  "(auth)/welcome.tsx",
  "(tabs)/_layout.tsx",
  "(tabs)/today.tsx",
  "(tabs)/visits/index.tsx",
  "(tabs)/visits/new.tsx",
  "(tabs)/visits/[visitId].tsx",
  "(tabs)/records.tsx",
  "(tabs)/wellbeing.tsx",
  "(tabs)/me/index.tsx",
  "(tabs)/me/learned.tsx",
];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

describe("route tree is exactly the 02 §4 nav map", () => {
  it.each(NAV_MAP)("%s exists", (route) => {
    expect(() => read(APP, route)).not.toThrow();
  });

  it("has no routes beyond the map (no stealth surfaces)", () => {
    const actual = walk(APP)
      .map((p) => p.slice(APP.length + 1))
      .sort();
    expect(actual).toEqual([...NAV_MAP].sort());
  });
});

describe("tab rail (02 §4)", () => {
  const layout = read(APP, "(tabs)/_layout.tsx");

  it.each(["today", "visits", "records", "wellbeing", "me"])("registers the %s trigger", (name) => {
    expect(layout).toContain(`name="${name}"`);
  });

  it("labels come from i18n, never literals", () => {
    for (const key of ["tabs.today", "tabs.visits", "tabs.records", "tabs.wellbeing", "tabs.me"]) {
      expect(layout).toContain(`t("${key}")`);
    }
  });

  it("wellbeing is consent-gated through visibleTabs — the single rule", () => {
    expect(layout).toContain("visibleTabs(account.consents)");
    expect(layout).toMatch(/tabs\.includes\("wellbeing"\)/);
  });
});

describe("design invariants as source facts", () => {
  it("dev test accounts render only behind __DEV__", () => {
    const welcome = read(APP, "(auth)/welcome.tsx");
    expect(welcome).toContain("__DEV__ ?");
    // No other screen may import the fixtures for rendering; the session
    // holds them after sign-in.
    for (const file of walk(APP)) {
      if (file.endsWith("welcome.tsx")) continue;
      expect(read(file), file).not.toContain("dev/accounts");
    }
  });

  it("the emergency colour is defined once, in the theme (02 §5.3)", () => {
    for (const file of walk(SRC)) {
      if (!/\.(ts|tsx)$/.test(file) || file.endsWith(join("lib", "theme.ts"))) continue;
      const source = read(file);
      expect(source, file).not.toMatch(/#B3261E|#E5756D/i);
    }
  });

  it("no text-transform uppercase anywhere (Turkish İ/ı rule, 00 §2)", () => {
    for (const file of walk(SRC)) {
      if (!/\.tsx?$/.test(file)) continue;
      expect(read(file), file).not.toMatch(/textTransform:\s*"uppercase"/);
    }
  });

  it("no banned filler tokens in the app source (invariant 17)", () => {
    // Tokens assembled so this spec never trips the repo-wide gate itself.
    const banned = new RegExp(
      ["TO" + "DO", "FIX" + "ME", "lor" + "em", "place" + "holder"].join("|"),
      "i",
    );
    for (const file of walk(SRC)) {
      expect(read(file), file).not.toMatch(banned);
    }
  });
});
