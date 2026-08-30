/**
 * INT-263 — content a patient cannot scroll to is content the app did not show.
 *
 * The defect this file exists to stop shipping again: `Screen` is a bare
 * SafeAreaView, so a route that renders more content than the viewport holds
 * simply loses the overflow. Swiping does nothing, because there is nothing
 * to swipe. INT-260 then handed the patient a control that makes every screen
 * taller on purpose — at the 2.0 rung the welcome screen's title sat under the
 * status bar and `welcome.body`, the one line that says what the app is, was
 * unreachable.
 *
 * Two properties are asserted here, and the second is what makes the first
 * worth having:
 *
 *  1. Routes are ENUMERATED FROM THE FILESYSTEM, never from a list kept by
 *     hand. A list stops covering the app the moment someone adds a screen and
 *     forgets to add the row — which is exactly how welcome was missed when
 *     thirteen screens were rewired around it.
 *  2. The overflow is measured at 2.0, not at the default. The regression is
 *     content height against viewport height, so a check that only ran at 1.0
 *     would have passed on welcome.tsx the day the defect shipped. The
 *     discriminating case is asserted below rather than described.
 *
 * WHAT THIS FILE CANNOT DO, said plainly: the vitest lane has no renderer and
 * this container has no simulator, so nothing here is a measurement of a
 * device. `contentHeight` is a MODEL — it lays the catalogue strings a route
 * declares into the reference phone's measure at the shipped type tokens. It
 * is wrong in both directions and deliberately so:
 *
 *  - it counts every branch in the file, including ones that never render
 *    together, so a branchy screen models taller than any single state of it;
 *  - it counts nothing that is not a catalogue key — card padding, control
 *    boxes, images, list rows, and every string a server or a fixture supplies.
 *
 * The first error makes the gate demand a scroll container on screens whose
 * shown branch might have fitted. That is the right way for a gate to be
 * wrong: a scroll container on a screen that fits costs the patient nothing,
 * and a screen without one that does not fit costs them the content. The
 * second error means "fits" is never a claim that a screen is safe, only that
 * this model cannot convict it — which is why rule 1 applies to every route
 * regardless of what the model says.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { tr, type MessageKey } from "@/lib/i18n/tr";
import { APP_STEPS } from "@/lib/prefs/appearance";
import { lineHeight, scaledSize, spacing, type TypeRole } from "@/lib/theme";

const APP = __dirname;
const MOBILE = join(APP, "..", "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/**
 * A route is any `.tsx` under `src/app` that expo-router turns into a screen.
 *
 * Excluded, and only these: `_layout.tsx` (chrome — it renders a navigator,
 * not content) and expo-router's `+`-prefixed framework files (`+html`,
 * `+native-intent`, `+api`, and `+not-found`, whose content is a single line
 * the framework owns). Everything else in the directory is a screen a patient
 * can reach, so everything else is enumerated — including screens that do not
 * exist yet, which is the whole point of walking the tree.
 */
interface Route {
  readonly name: string;
  readonly source: string;
}

const ROUTES: readonly Route[] = walk(APP)
  .filter((path) => {
    const file = basename(path);
    return (
      file.endsWith(".tsx") &&
      !file.includes(".test.") &&
      !file.startsWith("_") &&
      !file.startsWith("+")
    );
  })
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

function themedSource(): string {
  return readFileSync(join(MOBILE, "src", "components", "Themed.tsx"), "utf8");
}

/* ------------------------------------------------------------------ */
/* The enumeration itself                                              */
/* ------------------------------------------------------------------ */

describe("the sweep enumerates the app rather than a list of it", () => {
  it("walks src/app and finds every screen route", () => {
    // Twenty today (twenty-four .tsx files, four of them layouts). The bound
    // is a floor, not a pin: adding a screen must not fail this test, it must
    // make the new screen answer every rule below.
    expect(ROUTES.length).toBeGreaterThanOrEqual(20);
    const names = ROUTES.map((r) => r.name);
    expect(names).toContain("src/app/(auth)/welcome.tsx");
    expect(names).toContain("src/app/index.tsx");
    expect(names).toContain("src/app/(tabs)/visits/[visitId]/intake.tsx");
  });

  it("leaves out layouts and the framework files, and nothing else", () => {
    const excluded = walk(APP)
      .map((path) => relative(MOBILE, path).split(sep).join("/"))
      .filter((name) => name.endsWith(".tsx") && !ROUTES.some((r) => r.name === name));
    for (const name of excluded) {
      expect(basename(name), name).toMatch(/^[_+]/);
    }
  });

  it("this file is not itself shipped as a route", () => {
    // A `.test.ts` inside src/app matches expo-router's require.context, so
    // without an explicit block Metro would bundle a screen that imports
    // node:fs. The gate that stops that is asserted, not assumed.
    const metro = readFileSync(join(MOBILE, "metro.config.js"), "utf8");
    expect(metro).toContain("blockList");
    expect(metro).toMatch(/src.{0,20}app.{0,40}test/);
  });
});

/* ------------------------------------------------------------------ */
/* Rule 1 — a scroll container, or one line saying why not             */
/* ------------------------------------------------------------------ */

const SCROLL_CONTAINER = /<(ScrollScreen|ScrollView|FlatList|SectionList|FlashList)[\s/>]/;

/** Lists that virtualize. Nesting one inside a ScrollView is an RN defect. */
const VIRTUALIZED = /<(FlatList|SectionList|FlashList)[\s/>]/;

/**
 * The exemption, and it lives at the route's own definition so the reason
 * travels with the code rather than with a table someone has to find.
 *
 *   // scroll-exempt(redirect): forwards elsewhere; renders no content.
 *
 * The kind is a closed set because each kind is STRUCTURALLY checked below —
 * an exemption nobody can verify is an exemption anybody can write.
 */
const EXEMPT_KINDS = ["redirect", "list", "media"] as const;
type ExemptKind = (typeof EXEMPT_KINDS)[number];

interface Exemption {
  readonly kind: ExemptKind;
  readonly reason: string;
}

function exemption(route: Route): Exemption | null {
  const match = /\/\/ scroll-exempt\((\w+)\): (.+)/.exec(route.source);
  if (match === null) {
    return null;
  }
  expect(EXEMPT_KINDS, `${route.name} claims an unknown exemption kind`).toContain(match[1]);
  return { kind: match[1] as ExemptKind, reason: match[2].trim() };
}

function scrolls(route: Route): boolean {
  return SCROLL_CONTAINER.test(route.source);
}

describe("rule 1 — every route scrolls, or declares why it does not", () => {
  it.each(ROUTES.map((r) => [r.name, r] as const))("%s", (name, route) => {
    const declared = exemption(route);
    if (declared === null) {
      expect(scrolls(route), `${name} renders no scroll container and claims no exemption`).toBe(
        true,
      );
      return;
    }
    // An exemption is a claim that there is nothing to scroll — so a route
    // holding both is confused about which one is true.
    expect(scrolls(route), `${name} is exempt AND scrolls`).toBe(false);
    expect(declared.reason.length, `${name} exemption gives no reason`).toBeGreaterThan(20);
  });

  it("every exemption is honest about its own kind", () => {
    for (const route of ROUTES) {
      const declared = exemption(route);
      if (declared === null) {
        continue;
      }
      if (declared.kind === "redirect") {
        // Nothing to lose: it renders a redirect and no copy of its own.
        expect(route.source, route.name).toMatch(/<Redirect\b/);
        expect(route.source, route.name).not.toMatch(/<AppText\b/);
      }
      if (declared.kind === "list") {
        // It scrolls itself; the exemption is from being WRAPPED, not from
        // scrolling, and wrapping it would be the nested-VirtualizedList bug.
        expect(route.source, route.name).toMatch(VIRTUALIZED);
      }
      if (declared.kind === "media") {
        // A full-bleed surface has no reading text to lose. The moment it
        // carries copy it is a screen, and it scrolls like every other one.
        expect(route.source, route.name).not.toMatch(/\bt\("/);
      }
    }
  });

  it("no route nests a virtualized list inside a scroll container", () => {
    for (const route of ROUTES) {
      if (VIRTUALIZED.test(route.source)) {
        expect(route.source, `${route.name} nests a VirtualizedList`).not.toMatch(
          /<(ScrollScreen|ScrollView)[\s/>]/,
        );
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* Rule 2 — measured at 2.0, because that is where the defect lives    */
/* ------------------------------------------------------------------ */

/**
 * The reference phone. iPhone 16 Pro logical points — the device 00 §2's
 * large-text arithmetic and INT-260's rail measurements were taken on, so the
 * numbers here sit in the same coordinate system as the ones already shipped.
 */
const VIEWPORT = { width: 402, height: 874, insetTop: 62, insetBottom: 34 } as const;

/** The measure a line of copy actually gets, inside the screen padding. */
const MEASURE = VIEWPORT.width - 2 * spacing.screen;

/** The height content has before something falls off the bottom. */
const VIEWPORT_CONTENT =
  VIEWPORT.height - VIEWPORT.insetTop - VIEWPORT.insetBottom - 2 * spacing.screen;

/**
 * Average glyph advance as a fraction of the font size, for Inter set in
 * Turkish. Half an em is conservative for lowercase Latin with diacritics —
 * it over-estimates how much fits on a line, which under-estimates height,
 * which keeps the model a lower bound in the direction that matters.
 */
const GLYPH_ADVANCE = 0.5;

function linesFor(text: string, role: TypeRole, scale: number): number {
  const perLine = Math.max(1, Math.floor(MEASURE / (scaledSize(role, scale) * GLYPH_ADVANCE)));
  return Math.max(1, Math.ceil(text.length / perLine));
}

const ROLE_OR_KEY =
  /role="(display|hero|title|body|label|caption|micro)"|\bt\("([^"]+)"(?:,\s*\w+)?\)/g;

/**
 * The copy a route declares, in source order, each line at the role of the
 * nearest `role=` above it (`body` when a route states none — the AppText
 * default). Dynamic strings, fixtures and anything a server supplies are not
 * counted at all: only catalogue keys, because those are the ones invariant 5
 * makes the source of truth and the only ones a static reader can measure.
 * Branches are not resolved either — every key in the file counts once.
 */
function copyBlocks(source: string): { role: TypeRole; text: string }[] {
  const blocks: { role: TypeRole; text: string }[] = [];
  let role: TypeRole = "body";
  for (const match of source.matchAll(ROLE_OR_KEY)) {
    if (match[1] !== undefined) {
      role = match[1] as TypeRole;
      continue;
    }
    const key = match[2] as MessageKey;
    const text = tr[key];
    if (typeof text === "string") {
      blocks.push({ role, text });
    }
  }
  return blocks;
}

/** The modelled height of the route's declared copy at `scale` — see above. */
function contentHeight(source: string, scale: number): number {
  const blocks = copyBlocks(source);
  if (blocks.length === 0) {
    return 0;
  }
  const text = blocks.reduce(
    (total, block) =>
      total + linesFor(block.text, block.role, scale) * lineHeight(block.role, scale),
    0,
  );
  // The tightest rhythm any screen in the app uses between blocks.
  return text + spacing.md * (blocks.length - 1);
}

describe("rule 2 — the overflow is measured at the top of the INT-260 ladder", () => {
  it("2.0 is a rung the patient can actually choose", () => {
    expect(APP_STEPS[APP_STEPS.length - 1]).toBe(2.0);
  });

  it("the model is not vacuous — it grows with the scale and convicts real screens", () => {
    const welcome = ROUTES.find((r) => r.name === "src/app/(auth)/welcome.tsx")!;
    expect(contentHeight(welcome.source, 2.0)).toBeGreaterThan(contentHeight(welcome.source, 1.0));
    const overflowing = ROUTES.filter((r) => contentHeight(r.source, 2.0) > VIEWPORT_CONTENT);
    expect(overflowing.length).toBeGreaterThanOrEqual(5);
  });

  it("a check that only ran at 1.0 would have passed on welcome.tsx", () => {
    // This is the acceptance's own argument, as an assertion. The welcome
    // screen fits the phone at the default scale and does not fit it at the
    // rung Görünüm offers — which is why the defect shipped, and why the
    // sweep is proved at 2.0.
    const welcome = ROUTES.find((r) => r.name === "src/app/(auth)/welcome.tsx")!;
    expect(contentHeight(welcome.source, 1.0)).toBeLessThan(VIEWPORT_CONTENT);
    expect(contentHeight(welcome.source, 2.0)).toBeGreaterThan(VIEWPORT_CONTENT);
  });

  it.each(ROUTES.map((r) => [r.name, r] as const))(
    "%s keeps its content reachable at 2.0",
    (name, route) => {
      const height = contentHeight(route.source, 2.0);
      if (height <= VIEWPORT_CONTENT) {
        return;
      }
      expect(
        scrolls(route),
        `${name} models ${height} pt of copy at scale 2.0 into a ${VIEWPORT_CONTENT} pt viewport with no scroll container`,
      ).toBe(true);
    },
  );
});

/* ------------------------------------------------------------------ */
/* Rule 3 — the fix is a container, never a shrink                     */
/* ------------------------------------------------------------------ */

const SHRINKING_PROPS = [
  "numberOfLines",
  "ellipsizeMode",
  "adjustsFontSizeToFit",
  "minimumFontScale",
  "maxFontSizeMultiplier",
];

describe("rule 3 — no route closes its overflow by taking size back", () => {
  it("nothing truncates, ellipsizes or shrinks text to fit", () => {
    for (const prop of SHRINKING_PROPS) {
      const offenders = ROUTES.filter((r) => r.source.includes(prop)).map((r) => r.name);
      expect(offenders, prop).toEqual([]);
    }
  });

  it("no route clamps the scale the patient chose", () => {
    for (const route of ROUTES) {
      expect(route.source, route.name).not.toMatch(/Math\.min\([^)]*useFontScale/);
      expect(route.source, route.name).not.toMatch(/allowFontScaling=\{true\}/);
    }
  });
});

/* ------------------------------------------------------------------ */
/* Rule 4 — the padding rides on the content, not on the box           */
/* ------------------------------------------------------------------ */

describe("rule 4 — the scroll region reaches the full viewport", () => {
  it("ScrollScreen is the shared container, and it is flush", () => {
    const themed = themedSource();
    const body = /export function ScrollScreen\([\s\S]*?\n\}\n/.exec(themed);
    expect(body, "ScrollScreen is not declared the way this test reads it").not.toBeNull();
    // The padding is on the CONTENT, so the scrollable area and its indicator
    // run edge to edge; on the ScrollView's own style they would stop short.
    expect(body![0]).toContain(
      "contentContainerStyle={[styles.scrollContent, contentContainerStyle]}",
    );
    expect(themed).toMatch(/scrollContent:\s*\{[^}]*padding: spacing\.screen/);
    // flexGrow, not flex: short content still fills the viewport (so a
    // centred screen stays centred), tall content is free to exceed it.
    expect(themed).toMatch(/scrollContent:\s*\{[^}]*flexGrow: 1/);
    expect(themed).toMatch(/flush:\s*\{\s*flex: 1\s*\}/);
  });

  it("the plain Screen frame carries no padding of its own", () => {
    // The padded frame was the defect's other half: a ScrollView inside it is
    // inset on all four sides, so the scroll region — and the content that
    // scrolls through it — stops a screen padding short of the edge, which is
    // the opposite of what RAIL_EDGES promises. The frame is padding-free now,
    // so no screen can inherit an inset scroll region by accident.
    const themed = themedSource();
    expect(themed).not.toMatch(/screen:\s*\{[^}]*padding/);
    expect(themed).toMatch(
      /style=\{\[styles\.flush, \{ backgroundColor: theme\.background \}, style\]\}/,
    );
  });

  it("no route re-pads the frame around its own scroll container", () => {
    for (const route of ROUTES) {
      for (const tag of route.source.match(/<Screen\b[^>]*>/g) ?? []) {
        expect(tag, `${route.name} styles the Screen frame`).not.toMatch(/\sstyle=/);
      }
    }
  });

  it("no route puts a style prop on a scroll container", () => {
    for (const route of ROUTES) {
      for (const tag of route.source.match(/<ScrollView\b[^>]*>/g) ?? []) {
        expect(tag, `${route.name} styles the ScrollView box`).not.toMatch(/\sstyle=/);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* Rule 5 — the keyboard screens keep their field visible              */
/* ------------------------------------------------------------------ */

describe("rule 5 — a scroll container does not re-introduce the covered field", () => {
  const typing = ROUTES.filter((r) => /<TextInput[\s/>]/.test(r.source));

  it("finds the free-text routes it is supposed to police", () => {
    const names = typing.map((r) => r.name);
    expect(names).toContain("src/app/(auth)/phone.tsx");
    expect(names).toContain("src/app/(auth)/otp.tsx");
    expect(names.length).toBeGreaterThanOrEqual(4);
  });

  it.each(typing.map((r) => [r.name, r] as const))(
    "%s keeps its tap-through handling",
    (name, route) => {
      // Preserved, not re-derived: a ScrollView swallows the first tap on the
      // CTA while the keyboard is up unless it is told not to.
      expect(route.source, name).toContain('keyboardShouldPersistTaps="handled"');
    },
  );

  it("the shared container makes room for the keyboard", () => {
    // Without this the field can sit under the keyboard with no way to bring
    // it back — the covered-field defect, reintroduced by the fix for another.
    expect(themedSource()).toContain("automaticallyAdjustKeyboardInsets");
  });
});

/* ------------------------------------------------------------------ */
/* The one route that delegates its whole body to components           */
/* ------------------------------------------------------------------ */

describe("the intake route scrolls in all three of its phases", () => {
  // intake.tsx hands its body to one of three components by phase, so the
  // route-level check above passes on the branch that happens to hold the
  // ScrollView. Each branch is a full screen of its own and is named here.
  const branch = (file: string): string =>
    readFileSync(join(MOBILE, "src", "components", file), "utf8");

  it.each([["DialogueGate.tsx"], ["DialogueIntake.tsx"]])("%s scrolls", (file) => {
    expect(branch(file)).toMatch(SCROLL_CONTAINER);
  });

  it("the steps phase scrolls in the route file itself", () => {
    const intake = ROUTES.find((r) => r.name === "src/app/(tabs)/visits/[visitId]/intake.tsx")!;
    expect(intake.source).toMatch(SCROLL_CONTAINER);
  });
});
