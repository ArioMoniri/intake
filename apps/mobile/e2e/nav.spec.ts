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
  "(auth)/phone.tsx",
  "(auth)/otp.tsx",
  "(auth)/consent.tsx",
  "(tabs)/_layout.tsx",
  "(tabs)/today.tsx",
  "(tabs)/visits/_layout.tsx",
  "(tabs)/visits/index.tsx",
  "(tabs)/visits/new.tsx",
  "(tabs)/visits/[visitId]/index.tsx",
  "(tabs)/visits/[visitId]/intake.tsx",
  "(tabs)/visits/[visitId]/review.tsx",
  // INT-139 — Paylaşımlarınız: the share centre for this visit's note
  "(tabs)/visits/[visitId]/shares.tsx",
  // INT-311 — issuing a Doctor Link from the patient's phone (in-app only)
  "(tabs)/visits/[visitId]/issue-link.tsx",
  "(tabs)/records.tsx",
  "(tabs)/wellbeing.tsx",
  "(tabs)/me/index.tsx",
  // INT-260 — Görünüm: text size, theme, motion, start mode
  "(tabs)/me/appearance.tsx",
  // INT-140 — Verileriniz: the KVKK m.11 export/erasure controls
  "(tabs)/me/data.tsx",
  "(tabs)/me/learned.tsx",
  // INT-141 — Bildirimler: opt-out and quiet hours
  "(tabs)/me/notifications.tsx",
  // INT-133 — companions & the under-18 door (02 §4 me/companions)
  "(tabs)/me/companion.tsx",
  "(tabs)/me/consents/index.tsx",
  "(tabs)/me/consents/[purpose].tsx",
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

describe("tab rail (02 §4; floating pill since design pass 4)", () => {
  const layout = read(APP, "(tabs)/_layout.tsx");
  const rail = read(SRC, "components", "FloatingTabBar.tsx");

  it.each(["today", "visits", "records", "wellbeing", "me/index"])(
    "registers the %s screen",
    (name) => {
      expect(layout).toContain(`name="${name}"`);
    },
  );

  it("labels come from i18n, never literals (rail renders t(labelKey))", () => {
    for (const key of ["tabs.today", "tabs.visits", "tabs.records", "tabs.wellbeing", "tabs.me"]) {
      expect(rail).toContain(`labelKey: "${key}"`);
    }
    expect(rail).toContain("t(meta.labelKey)");
  });

  it("wellbeing is consent-gated through visibleTabs — the single rule", () => {
    expect(layout).toContain("visibleTabs(consents)");
    expect(layout).toMatch(/tabs\.includes\("wellbeing"\)/);
  });

  it("the gate UNREGISTERS the route (Tabs.Protected), never just hides it", () => {
    expect(layout).toMatch(/Tabs\.Protected guard=\{tabs\.includes\("wellbeing"\)\}/);
  });

  it("native tabs stay superseded (owner decision 2026-08-28, pass 4)", () => {
    // The Oura floating pill replaced NativeTabs for the dev tier; the
    // native-tabs import creeping back in is a regression against that call.
    expect(layout).not.toContain("unstable-native-tabs");
    expect(layout).toContain("FloatingTabBar");
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
    // Case follows the repo-wide gate script, which is the authority: its
    // grep -E is case-SENSITIVE, so the marker tokens are uppercase and the
    // prose tokens lowercase. The "i" flag this spec used to carry made it
    // stricter than that gate in a way that flagged DATA rather than filler
    // — "Ortodonti", a Turkish dental branch in the INT-042 taxonomy,
    // contains the letters of the lowercased marker token.
    const markers = new RegExp(["TO" + "DO", "FIX" + "ME"].join("|"));
    const prose = new RegExp(["lor" + "em", "place" + "holder"].join("|"), "i");
    for (const file of walk(SRC)) {
      const source = read(file);
      expect(source, file).not.toMatch(markers);
      expect(source, file).not.toMatch(prose);
    }
  });
});
