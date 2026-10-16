/**
 * INT-260 — Görünüm: the settings screen, and the four mechanisms that make
 * its controls do something.
 *
 * Same shape and the same reason as a11y.spec.ts: React Native has no DOM, so
 * a rendered assertion needs a device. What CAN be proved from the tree is
 * that the wiring exists — that `useFontScale` reads the stored step, that
 * every scheme consumer goes through the one hook that can be overridden,
 * that the stack header stopped hardcoding 17 pt, and that the rail collapses
 * at the scale theme.ts has claimed since INT-130.
 *
 * The two things this file cannot prove — that the screen survives its own
 * largest setting, and that the change propagates to another screen — are
 * simulator screenshots in docs/evidence/INT-260.md, taken at both ends of
 * the ladder.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { MIN_TAP } from "../src/lib/a11y/target";
import {
  APP_STEPS,
  LARGE_TEXT_SCALE,
  RAIL_LABEL_MAX_SCALE,
  railWellSize,
  shouldStack,
} from "../src/lib/prefs/appearance";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const APP = join(SRC, "app");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const TREE: { name: string; source: string }[] = walk(SRC)
  .filter((p) => /\.tsx?$/.test(p) && !p.includes(".test."))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/** Modules that import a named symbol straight from react-native. */
function importersOf(symbol: string): string[] {
  const pattern = new RegExp(
    `import\\s*\\{[^}]*\\b${symbol}\\b[^}]*\\}\\s*from\\s*["']react-native["']`,
    "s",
  );
  return TREE.filter((f) => pattern.test(f.source)).map((f) => f.name);
}

it("the scanner sees the tree it is supposed to police", () => {
  expect(TREE.length).toBeGreaterThan(40);
});

/* ------------------------------------------------------------------ */
/* The screen exists, is reachable, and is the only new surface        */
/* ------------------------------------------------------------------ */

describe("Görünüm is a real, reachable screen", () => {
  it("has a route, registered in the tabs layout", () => {
    expect(file("src/app/(tabs)/me/appearance.tsx")).toContain("export default");
    expect(file("src/app/(tabs)/_layout.tsx")).toContain('name="me/appearance"');
  });

  it("Profilim carries the entry row, above İzinleriniz", () => {
    const me = file("src/app/(tabs)/me/index.tsx");
    expect(me).toContain('router.push("/(tabs)/me/appearance")');
    expect(me.indexOf('"/(tabs)/me/appearance"')).toBeLessThan(me.indexOf('"/(tabs)/me/consents"'));
  });

  it("the screen's label and title are one key, used at both sites", () => {
    expect(file("src/app/(tabs)/me/index.tsx")).toContain('t("appearance.title")');
    expect(file("src/app/(tabs)/me/appearance.tsx")).toContain('t("appearance.title")');
  });
});

/* ------------------------------------------------------------------ */
/* T-21 · text size — the override, in place                           */
/* ------------------------------------------------------------------ */

describe("T-21 — useFontScale overrides the OS value rather than composing with it", () => {
  const themed = () => file("src/components/Themed.tsx");

  it("useFontScale reads the stored step and the OS value, and nothing else", () => {
    const body = /export function useFontScale\(\): number \{([\s\S]*?)\n\}/.exec(themed());
    expect(body, "useFontScale is not declared the way this test reads it").not.toBeNull();
    expect(body![1]).toContain("useWindowDimensions().fontScale");
    expect(body![1]).toContain("effectiveFontScale(");
  });

  it("the composition operator appears nowhere in the resolution path", () => {
    // The whole of R4 in one assertion: neither the hook nor the pure function
    // it delegates to may multiply. `allowFontScaling={false}` exists to stop
    // exactly this, and a second multiplier reintroduces it by hand.
    const body = /export function useFontScale\(\): number \{([\s\S]*?)\n\}/.exec(themed())![1];
    expect(body).not.toMatch(/[*]/);
    const pure = /export function effectiveFontScale\([\s\S]*?\n\}/.exec(
      file("src/lib/prefs/appearance.ts"),
    );
    expect(pure).not.toBeNull();
    expect(pure![0]).not.toMatch(/[*]/);
  });

  it("no sibling hook was added — there is one scale input for the whole app", () => {
    const hooks = TREE.filter((f) => /export function use[A-Za-z]*FontScale/.test(f.source)).map(
      (f) => f.name,
    );
    expect(hooks).toEqual(["src/components/Themed.tsx"]);
  });

  it("AppText, scaledSize, lineHeight and the clamp are untouched by the override", () => {
    // The override changes ONE input. If it had reached into the token layer,
    // "scales once" would stop being true by construction.
    expect(themed()).toContain("allowFontScaling={false}");
    expect(themed()).toContain("fontSize: scaledSize(role, fontScale)");
    const theme = file("src/lib/theme.ts");
    expect(theme).toContain("Math.max(0.5, Math.min(fontScale, 2.0))");
    expect(theme).not.toContain("APP_STEPS");
  });

  it("the five bare TextInput call sites still take the same hook", () => {
    const inputs = TREE.filter((f) => /<TextInput[\s/>]/.test(f.source)).map((f) => f.name);
    expect(inputs.length).toBeGreaterThanOrEqual(5);
    for (const name of inputs) {
      expect(file(name), name).toContain("useFontScale()");
    }
  });
});

/* ------------------------------------------------------------------ */
/* T-22 · theme — one overridable hook, every consumer on it           */
/* ------------------------------------------------------------------ */

/**
 * The one file still reading the OS scheme directly, with its reason.
 *
 * `DialogueIntake.tsx` is being rewritten in the same wave (the stance-machine
 * issue owns it end to end), and its two uses of the boolean choose a border
 * colour rather than a palette — `useTheme()` already carries the override
 * there. Re-pointing one line into a file under a full rewrite buys a merge
 * conflict and no behaviour. It moves when that rewrite lands.
 *
 * May only shrink.
 */
const OS_SCHEME_EXCEPTIONS: string[] = [];

describe("T-22 — the colour scheme has one overridable source", () => {
  it("useColorScheme is imported from react-native only where it is resolved", () => {
    expect(importersOf("useColorScheme").sort()).toEqual(
      ["src/components/Themed.tsx", ...OS_SCHEME_EXCEPTIONS].sort(),
    );
  });

  it("every other consumer takes the resolved hook", () => {
    const consumers = TREE.filter((f) => /\buseScheme\(\)/.test(f.source)).map((f) => f.name);
    // ListRow left this list in INT-422: it takes useTheme(), which resolves
    // through useScheme() (asserted below).
    expect(consumers).toContain("src/components/FloatingTabBar.tsx");
    expect(consumers).toContain("src/components/GlassBar.tsx");
    expect(consumers).toContain("src/components/SectionPanel.tsx");
    // The typed intake left this list in INT-433: its chips take their fills
    // from palette tokens in both schemes, through useTheme().
  });

  it("useScheme resolves the stored override, and useTheme goes through it", () => {
    const themed = () => file("src/components/Themed.tsx");
    expect(themed()).toContain("resolveScheme(");
    const useTheme = /export function useTheme\(\): ThemeColors \{([\s\S]*?)\n\}/.exec(themed());
    expect(useTheme).not.toBeNull();
    expect(useTheme![1]).toContain("useScheme()");
  });

  it("the exception list is honest — every file on it still reads the OS directly", () => {
    for (const name of OS_SCHEME_EXCEPTIONS) {
      expect(file(name), name).toContain("useColorScheme()");
    }
  });
});

/* ------------------------------------------------------------------ */
/* Reduced motion — OR, never override                                 */
/* ------------------------------------------------------------------ */

describe("the motion switch adds to the OS setting, it does not replace it", () => {
  const prefs = () => file("src/lib/a11y/prefs.ts");

  it("useReducedMotion folds the stored override in", () => {
    expect(prefs()).toContain("useAppearance()");
    expect(prefs()).toContain("reducedMotion(");
  });

  it("its five call sites are untouched — the policy moved, not the callers", () => {
    const callers = TREE.filter(
      (f) => /useReducedMotion\(\)/.test(f.source) && f.name !== "src/lib/a11y/prefs.ts",
    ).map((f) => f.name);
    expect(callers.length).toBeGreaterThanOrEqual(5);
    for (const name of callers) {
      expect(file(name), name).toContain('from "@/lib/a11y/prefs"');
    }
  });
});

/* ------------------------------------------------------------------ */
/* T-19 · the stack header, which hardcoded 17 pt                      */
/* ------------------------------------------------------------------ */

describe("T-19 — the pushed-screen title scales with everything else", () => {
  const themed = () => file("src/components/Themed.tsx");

  it("sizes from scaledSize rather than a literal", () => {
    const body = /export function useStackHeader\(\)[\s\S]*?\n\}/.exec(themed());
    expect(body).not.toBeNull();
    expect(body![0]).toContain('scaledSize("body", fontScale)');
    expect(body![0]).not.toMatch(/fontSize:\s*\d/);
  });

  it("turns react-navigation's own multiplier off, so it scales once here too", () => {
    // The header title is NOT an AppText: react-navigation renders it and
    // defaults allowFontScaling to ON. Sizing it from scaledSize without this
    // is the doubled-scale defect a11y.spec.ts:321 forbids for TextInput.
    expect(themed()).toContain("headerTitleAllowFontScaling: false");
  });
});

/* ------------------------------------------------------------------ */
/* T-20 · the rail collapse theme.ts has promised since INT-130        */
/* ------------------------------------------------------------------ */

describe("T-20 — the tab rail changes FORM at the large-text scale", () => {
  const rail = () => file("src/components/FloatingTabBar.tsx");

  it("reads the effective scale and its own measured threshold", () => {
    expect(rail()).toContain("useFontScale()");
    expect(rail()).toContain("railCollapses(");
  });

  it("drops the micro captions rather than shrinking or truncating them", () => {
    // 00 §2: a screen that cannot survive 2.0 changes form; it never clamps
    // text harder. `micro` is 11 pt chrome and there is nothing below it.
    expect(rail()).toMatch(/collapsed\s*\?\s*null\s*:/);
  });

  it("the collapsed item still reaches the target floor", () => {
    expect(rail()).toContain("minHeight: MIN_TAP");
    expect(rail()).toContain("minWidth: MIN_TAP");
    expect(MIN_TAP).toBe(44);
  });

  it("the glyph and its box GROW with the text, not just lose their caption", () => {
    // The owner's report, verbatim: "navbar and sizes dont match". Dropping
    // the captions without growing the icons left a small-chrome rail under
    // doubled body text — the label-drop is half the form change, and on its
    // own it reads as a different app's navbar pasted under the content.
    expect(rail()).toContain("scaledControl(");
    expect(rail()).not.toMatch(/size=\{20\}/);
  });

  it("the active item is still not carried by colour alone once the label is gone", () => {
    // With the caption dropped, tint would be the only difference between the
    // focused tab and the rest — BK8 / SC 1.4.1. A filled well behind the
    // active glyph is a shape difference, and the name still carries the state.
    expect(rail()).toContain("accessibilityState={{ selected: active }}");
    expect(rail()).toContain("styles.activeWell");
  });

  it("theme.ts states no threshold it does not own", () => {
    // It claimed "the rail collapses at ≥1.6" for four design passes while
    // FloatingTabBar held no scale reference at all, and the number was wrong
    // when something finally rendered against it. Both thresholds now live in
    // lib/prefs/appearance.ts, where a test can reach them.
    const theme = file("src/lib/theme.ts");
    expect(theme).toContain("LARGE_TEXT_SCALE");
    expect(theme).toContain("RAIL_LABEL_MAX_SCALE");
    expect(theme).not.toMatch(/rail collapses at .1\.6/);
    expect(LARGE_TEXT_SCALE).toBe(1.6);
    expect(RAIL_LABEL_MAX_SCALE).toBe(1.2);
  });
});

describe("chrome and content move together (the owner's report)", () => {
  it("the space reserved under the rail is the rail's own height, not a constant", () => {
    // It was `TAB_BAR_CLEARANCE = 120`, sized for a scale-1.0 pill. Once the
    // rail grew with the text those became two numbers free to drift, and
    // content ran underneath the navbar. One source now feeds both.
    const rail = file("src/components/FloatingTabBar.tsx");
    expect(rail).toContain("export function useTabBarClearance()");
    expect(rail).toContain("railWellSize(fontScale, MIN_TAP)");
    expect(rail).toContain('scaledSize("body", fontScale)');
  });

  it("no screen still reserves a fixed constant for it", () => {
    const constants = TREE.filter((f) => /TAB_BAR_CLEARANCE/.test(f.source)).map((f) => f.name);
    expect(constants).toEqual([]);
  });

  it("every rail screen takes the scaling clearance", () => {
    const users = TREE.filter((f) => /useTabBarClearance\(\)/.test(f.source)).map((f) => f.name);
    // The rail itself plus the twelve screens that scroll under it.
    expect(users.length).toBeGreaterThanOrEqual(13);
    expect(users).toContain("src/app/(tabs)/today.tsx");
    expect(users).toContain("src/app/(tabs)/me/appearance.tsx");
  });

  it("the well never drops below the target floor, whatever the glyph does", () => {
    for (const step of APP_STEPS) {
      expect(railWellSize(step, MIN_TAP), String(step)).toBeGreaterThanOrEqual(MIN_TAP);
    }
    // And it does grow — a well pinned at MIN_TAP is the defect, not the fix.
    expect(railWellSize(2.0, MIN_TAP)).toBeGreaterThan(railWellSize(1.0, MIN_TAP));
  });

  it("the prep gauge's arc scales with the numeral it frames, and is capped to the screen", () => {
    // A fixed 232 pt arc around a 112 pt numeral read as a broken ring.
    const gauge = file("src/components/PrepGauge.tsx");
    expect(gauge).toContain("scaledControl(BASE_SIZE, fontScale)");
    expect(gauge).toContain("useWindowDimensions()");
    expect(gauge).toContain("Math.min(");
  });
});

/* ------------------------------------------------------------------ */
/* 00 §2 — never truncate mid-word in Turkish                          */
/* ------------------------------------------------------------------ */

describe("00 §2 — a Turkish word never loses its suffix", () => {
  it("nothing in the app can truncate a string", () => {
    // The clinical hazard 00 §2 records: `ağrımıyor` cut to `ağrım…` turns
    // "it doesn't hurt" into "my pain". The Python gate in
    // tests/release/test_i18n_complete.py is the build gate 00 asks for and
    // scans the whole shipped tree; this is its mirror for the render tree, so
    // a mobile-only change fails without waiting for the Python fan-out.
    for (const token of ["numberOfLines", "ellipsizeMode", "adjustsFontSizeToFit"]) {
      const offenders = TREE.filter((f) => f.source.includes(token)).map((f) => f.name);
      expect(offenders, token).toEqual([]);
    }
  });

  it("the residual wrap is a MEASURE problem, and the measure is already maximal", () => {
    // Measured on an iPhone 16 Pro at 2.0: `Hastalıkları` needs ~371 pt and the
    // widest measure a card can offer is ~330. Swapping the serif for the sans
    // was tried and bought nothing at this size, so it was reverted rather than
    // shipped as an unjustified change to the app's register. The remaining
    // levers are truncation (banned, and now impossible — see above) or
    // shrinking the text (banned by 00 §2), so what is left is a copy decision.
    // This pins that the two banned levers stay unused on the display roles.
    const themed = file("src/components/Themed.tsx");
    expect(themed).toContain("fontSize: scaledSize(role, fontScale)");
    expect(themed).not.toContain("adjustsFontSizeToFit");
    expect(themed).not.toContain("minimumFontScale");
  });

  it("a card gives its measure priority over its air at large text", () => {
    // The width a long Turkish word needs is the only thing that stops React
    // Native breaking it, and taking padding back costs the patient nothing —
    // unlike shrinking the text they just chose to enlarge.
    // INT-422: the card's padding IS the tight measure, the 16 pt content
    // margin, at every scale, so there is no air left to give back.
    const themed = file("src/components/Themed.tsx");
    expect(themed).toMatch(/ {2}card: \{[^}]*padding: spacing\.md,/);
    expect(themed).not.toMatch(/ {2}card: \{[^}]*padding: spacing\.(?:lg|xl),/);
  });
});

/* ------------------------------------------------------------------ */
/* T-17 · the two new controls                                         */
/* ------------------------------------------------------------------ */

describe("T-17 — Segmented is a radio group, not five buttons", () => {
  const segmented = () => file("src/components/Segmented.tsx");

  it("the container declares the group and its name", () => {
    expect(segmented()).toContain('accessibilityRole="radiogroup"');
    expect(segmented()).toContain("accessibilityLabel={label}");
  });

  it("each option is a radio that says whether it is the chosen one", () => {
    expect(segmented()).toContain('accessibilityRole="radio"');
    expect(segmented()).toContain("accessibilityState={{ selected");
  });

  it("rows reach the target floor by box, never by slop", () => {
    expect(segmented()).toContain("minHeight: MIN_TAP");
    expect(segmented()).not.toContain("hitSlop");
  });

  it("stacks vertically at the large-text scale, where a row of five cannot fit", () => {
    expect(segmented()).toContain("shouldStack(");
    expect(segmented()).toContain("useFontScale()");
  });

  it("also stacks a group too wide for the phone at ANY scale", () => {
    // Measured on the simulator at OS 1.0: five Turkish labels in one row put
    // "Daha büyük" and "En büyük" onto two lines each and left the pills at
    // different heights. The control changes form; the copy is not shortened
    // to fit it.
    expect(shouldStack(1.0, 2)).toBe(false);
    expect(shouldStack(1.0, 3)).toBe(false);
    expect(shouldStack(1.0, 4)).toBe(true);
    expect(shouldStack(1.0, 5)).toBe(true);
    expect(shouldStack(LARGE_TEXT_SCALE, 2)).toBe(true);
  });

  it("selection is marked by more than a fill once the rows stack", () => {
    expect(segmented()).toContain("checkmark");
  });
});

describe("T-17 — SwitchRow is a switch, with its state", () => {
  const row = () => file("src/components/SwitchRow.tsx");

  it("declares the platform role and the value", () => {
    expect(row()).toContain('accessibilityRole="switch"');
    // INT-472 adds the read-only state beside the value.
    expect(row()).toMatch(/accessibilityState=\{\{ checked(?:, disabled)? \}\}/);
  });

  it("the whole row is the target, so it clears the floor by box", () => {
    expect(row()).toContain("minHeight: 56");
    expect(row()).not.toContain("hitSlop");
  });

  it("the knob moves as well as recolouring — state is never hue alone", () => {
    expect(row()).toContain("alignItems: checked");
  });

  it("the toggle grows with its label rather than staying at its base size", () => {
    expect(row()).toContain("scaledControl(");
    expect(row()).toContain("useFontScale()");
  });

  it("the toggle takes its own line once the label needs two", () => {
    // At 2.0 "Ekran hareketini azaltın" wraps and a right-aligned toggle reads
    // as an afterthought beside it. Above the large-text scale the row becomes
    // a column, so the control sits under the words it governs.
    expect(row()).toContain("isLargeText(");
    expect(row()).toContain("styles.rowStacked");
  });
});

/* ------------------------------------------------------------------ */
/* T-18 · the preview shows the product, not a fabricated patient       */
/* ------------------------------------------------------------------ */

describe("T-18 — the preview is real product copy", () => {
  const screen = () => file("src/app/(tabs)/me/appearance.tsx");

  it("renders catalogue keys the intake pack already ships", () => {
    expect(screen()).toContain('t("intake.q.complaint")');
    expect(screen()).toContain('t("intake.opt.pain")');
  });

  it("invents no clinical content of its own", () => {
    // A plausible utterance ("İki gündür başım ağrıyor.") is demo clinical
    // data — invariant 17. Every visible string on this screen is a key.
    const keys = [...screen().matchAll(/t\("([^"]+)"\)/g)].map((m) => m[1]);
    expect(keys.length).toBeGreaterThan(10);
    const tr = file("src/lib/i18n/tr.ts");
    const en = file("src/lib/i18n/en.ts");
    for (const key of keys) {
      expect(tr, key).toContain(`"${key}"`);
      expect(en, key).toContain(`"${key}"`);
    }
  });

  it("offers no free numeric entry and no continuous control (invariant 22, R5)", () => {
    expect(screen()).not.toMatch(/<TextInput[\s/>]/);
    expect(screen()).not.toMatch(/Slider|onValueChange|keyboardType/);
  });

  it("holds no timer — a settings screen takes nothing away on a clock", () => {
    expect(screen()).not.toMatch(/setTimeout|setInterval/);
  });

  it("the preview is announced as what it is", () => {
    expect(screen()).toContain('t("a11y.appearance.preview")');
  });
});

/* ------------------------------------------------------------------ */
/* Persistence — device-local, and provably so                          */
/* ------------------------------------------------------------------ */

describe("the preferences never leave the phone", () => {
  const provider = () => file("src/lib/prefs/AppearanceProvider.tsx");

  it("writes to this device's keychain slot only", () => {
    expect(provider()).toContain("APPEARANCE_SLOT");
    expect(provider()).toContain("WHEN_UNLOCKED_THIS_DEVICE_ONLY");
  });

  it("reaches no network, no session and no note", () => {
    // The inventory annotation says `recipients: none`; this is what makes
    // that a fact rather than a claim.
    expect(provider()).not.toMatch(/fetch\(|apiFetch|from "@\/lib\/(api|session|intake)/);
  });

  it("carries the invariant-18 inventory annotation beside the record", () => {
    for (const field of ["category", "purpose", "basis", "retention", "recipients"]) {
      expect(file("src/lib/prefs/appearance.ts"), field).toContain(field);
    }
  });

  it("every step of the ladder is offered — none is unreachable from the control", () => {
    const screen = file("src/app/(tabs)/me/appearance.tsx");
    // The screen carries option KEYS rather than resolved strings — `t()` at
    // module scope would freeze the labels in the import-time locale — so the
    // key is what proves the rung is offered.
    for (const rung of ["s", "m", "l", "xl", "xxl"]) {
      expect(screen, rung).toContain(`"appearance.size.${rung}"`);
    }
    expect(APP_STEPS.length).toBe(5);
  });
});
